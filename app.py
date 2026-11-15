#!/usr/bin/env python3
"""B2 Browser: tiny web GUI over the official `b2` CLI. Stdlib only."""
import base64, hmac, json, mimetypes, os, subprocess, tempfile, threading, time, uuid
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "127.0.0.1")
PASSWORD = os.environ.get("B2UI_PASSWORD", "")  # optional HTTP basic auth (any username)
INDEX = Path(__file__).with_name("index.html")
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "~/.b2-browser")).expanduser()
CONFIG, ACCOUNT_INFO = CONFIG_DIR / "config.json", CONFIG_DIR / "account_info"
JOBS = {}  # ponytail: in-memory job list, lost on restart; persist if you need history
DL_AUTH = {}  # bucket -> (download base url, token, expiry)


def creds():
    """Keys saved in Settings win; otherwise B2_APPLICATION_KEY_ID/B2_APPLICATION_KEY env vars."""
    c = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if c.get("keyId"):
        return c["keyId"], c.get("key", ""), "settings"
    kid = os.environ.get("B2_APPLICATION_KEY_ID", "")
    return kid, os.environ.get("B2_APPLICATION_KEY", ""), "env" if kid else None


def b2_env():
    # own account-info cache: never reads or writes the user's ~/.b2_account_info
    kid, key, src = creds()
    if not src:
        raise ValueError("Not configured. Open Settings and enter a B2 application key.")
    return {**os.environ, "B2_APPLICATION_KEY_ID": kid, "B2_APPLICATION_KEY": key,
            "B2_ACCOUNT_INFO": str(ACCOUNT_INFO), "B2_ESCAPE_CONTROL_CHARACTERS": "0"}


def b2(*args):
    r = subprocess.run(["b2", *args], capture_output=True, text=True, env=b2_env())
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout


def uri(bucket, path=""):
    if not bucket or "/" in bucket:
        raise ValueError("bad bucket")
    return f"b2://{bucket}/{path.lstrip('/')}"


def direct_url(bucket, path):
    """Pre-authorised B2 URL, so the browser streams previews (with seeking) straight from Backblaze.
    Needs the key's shareFiles capability; one token per bucket, refreshed daily."""
    base, tok, exp = DL_AUTH.get(bucket, (None, None, 0))
    if time.time() > exp:
        base = json.loads(b2("account", "get"))["downloadUrl"]
        tok = b2("bucket", "get-download-auth", "--duration", "86400", bucket).strip()
        DL_AUTH[bucket] = (base, tok, time.time() + 82800)
    return f"{base}/file/{quote(bucket)}/{quote(path)}?Authorization={quote(tok)}"


def start_job(label, *cmds):
    """Run b2 commands one after another; stop at the first failure (so a move never deletes after a failed copy)."""
    jid = uuid.uuid4().hex[:8]
    env = b2_env()
    job = JOBS[jid] = {"id": jid, "label": label, "status": "running", "log": [], "proc": None}

    def pump():
        for args in cmds:
            if job["status"] != "running":
                return
            proc = job["proc"] = subprocess.Popen(["b2", *args], stdout=subprocess.PIPE,
                                                  stderr=subprocess.STDOUT, env=env)
            buf = b""
            while chunk := proc.stdout.read(512):
                buf += chunk.replace(b"\r", b"\n")  # progress bars redraw with \r
                *lines, buf = buf.split(b"\n")
                job["log"] = (job["log"] + [l.decode(errors="replace") for l in lines if l.strip()])[-200:]
            if rc := proc.wait():
                job["status"] = "cancelled" if rc < 0 else f"failed ({rc})"
                return
        job["status"] = "done"

    threading.Thread(target=pump, daemon=True).start()
    return jid


def local_path(p):
    p = (p or "").strip()
    if not p or p.startswith("-"):
        raise ValueError("bad local path")
    return str(Path(p).expanduser())


class H(BaseHTTPRequestHandler):
    def send(self, code, body=b"", ctype="application/json", headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authed(self):
        if not PASSWORD:
            return True
        h = self.headers.get("Authorization", "")
        try:
            ok = h.startswith("Basic ") and hmac.compare_digest(
                base64.b64decode(h[6:]).decode().split(":", 1)[1], PASSWORD)
        except Exception:
            ok = False
        if not ok:
            self.send(401, b"auth required", "text/plain", [("WWW-Authenticate", 'Basic realm="b2"')])
        return ok

    def handle_any(self, method):
        if not self.authed():
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            route = getattr(self, f"{method}_{u.path.strip('/').replace('/', '_') or 'index'}", None)
            if not route:
                return self.send(404, {"error": "not found"})
            route(q)
        except (RuntimeError, ValueError) as e:
            self.send(400, {"error": str(e)})

    def do_GET(self):
        self.handle_any("get")

    def do_POST(self):
        self.handle_any("post")

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    # --- routes ---
    def get_index(self, q):
        self.send(200, INDEX.read_bytes(), "text/html; charset=utf-8")

    def get_api_buckets(self, q):
        self.send(200, [b["bucketName"] for b in json.loads(b2("bucket", "list", "--json"))])

    def get_api_ls(self, q):
        # `ls -l`, not `--json`: the JSON output omits folders.
        # Line: fileId action date time(UTC) size name  (folders: "- - - - 0 name/")
        out = []
        for line in b2("ls", "-l", uri(q.get("bucket"), q.get("prefix", ""))).splitlines():
            f = line.split(None, 5)
            if len(f) < 6 or f[1] == "hide" or f[5].endswith("/.bzEmpty"):
                continue
            folder = f[0] == "-"
            t = 0 if folder else int(datetime.fromisoformat(f"{f[2]}T{f[3]}+00:00").timestamp() * 1000)
            out.append({"name": f[5], "size": int(f[4]), "time": t, "folder": folder})
        self.send(200, out)

    def stream(self, bucket, path, ctype, disposition, limit=None):
        proc = subprocess.Popen(["b2", "file", "cat", uri(bucket, path)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=b2_env())
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(path.rsplit('/', 1)[-1])}")
        self.end_headers()
        sent = 0
        try:
            while (limit is None or sent < limit) and (chunk := proc.stdout.read(1 << 20)):
                self.wfile.write(chunk)
                sent += len(chunk)
        finally:
            proc.kill()

    def get_api_download(self, q):
        self.stream(q.get("bucket"), q.get("path", ""), "application/octet-stream", "attachment")

    def get_api_preview(self, q):
        bucket, path = q.get("bucket"), q.get("path", "")
        uri(bucket, path)  # validate
        if q.get("text"):  # same-origin so the page can fetch() it; first 512 KB is plenty to read
            return self.stream(bucket, path, "text/plain; charset=utf-8", "inline", 512 << 10)
        try:
            self.send(302, b"", "text/plain", [("Location", direct_url(bucket, path)),
                                               ("Cache-Control", "private, max-age=3000")])
        except RuntimeError:  # key lacks shareFiles: proxy through here instead (plays, but no seeking)
            self.stream(bucket, path, mimetypes.guess_type(path)[0] or "application/octet-stream", "inline")

    def post_api_upload(self, q):
        # raw body = file bytes (no multipart); spooled to disk so b2 can do parallel large-file upload
        uri(q.get("bucket"), q.get("path", ""))  # validate
        if not q.get("path", "").strip("/"):
            raise ValueError("missing path")
        n = int(self.headers.get("Content-Length", 0))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            while n > 0:
                chunk = self.rfile.read(min(n, 1 << 20))
                if not chunk:
                    break
                f.write(chunk)
                n -= len(chunk)
        try:
            b2("file", "upload", "--no-progress", q["bucket"], f.name, q["path"].lstrip("/"))
        finally:
            os.unlink(f.name)
        self.send(200, {"ok": True})

    def post_api_rm(self, q):
        d = self.body()
        args = ["rm", "--no-progress"] + (["-r"] if d.get("folder") else [])
        b2(*args, uri(d.get("bucket"), d.get("path", "")))
        self.send(200, {"ok": True})

    def post_api_sync(self, q):
        # direction "up": local -> b2 (backup); "down": b2 -> local (restore)
        d = self.body()
        remote, local = uri(d.get("bucket"), d.get("prefix", "")), local_path(d.get("local"))
        src, dst = (local, remote) if d.get("direction") == "up" else (remote, local)
        args = ["sync"] + (["--delete"] if d.get("delete") else []) + (["--dry-run"] if d.get("dryRun") else [])
        self.send(200, {"id": start_job(f"{src} → {dst}", args + [src, dst])})

    def post_api_mkdir(self, q):
        # B2 has no real folders; a zero-byte placeholder makes one appear (same as the B2 web console)
        d = self.body()
        path = d.get("path", "").strip("/")
        if not path:
            raise ValueError("missing folder name")
        uri(d.get("bucket"), path)  # validate
        with tempfile.NamedTemporaryFile() as f:
            b2("file", "upload", "--no-progress", d["bucket"], f.name, f"{path}/.bzEmpty")
        self.send(200, {"ok": True})

    def post_api_mv(self, q):
        d = self.body()
        folder = bool(d.get("folder"))
        src, dst = d.get("path", "").strip("/"), d.get("dest", "").strip().strip("/")
        if not src or not dst:
            raise ValueError("missing path")
        if folder:
            src, dst = src + "/", dst + "/"
            if dst.startswith(src):
                raise ValueError("can't move a folder into itself")
        if src == dst:
            raise ValueError("source and destination are the same")
        s, t = uri(d.get("bucket"), src), uri(d.get("bucket"), dst)
        # refuse to merge or overwrite: deleting the source afterwards could otherwise lose data
        if b2("ls", t).strip():
            raise ValueError(f"something already exists at {dst}")
        if folder:  # sync does parallel server-side copies; nothing passes through this machine
            jid = start_job(f"move {s} → {t}", ["sync", "--no-progress", s, t], ["rm", "-r", "--no-progress", s])
        else:
            jid = start_job(f"move {s} → {t}", ["file", "server-side-copy", s, t], ["rm", "--no-progress", s])
        self.send(200, {"id": jid})

    def get_api_settings(self, q):
        kid, _, src = creds()
        self.send(200, {"keyId": kid, "source": src})  # never send the secret back

    def post_api_settings(self, q):
        d = self.body()
        kid, key = d.get("keyId", "").strip(), d.get("key", "").strip()
        if not kid or not key:
            raise ValueError("Key ID and application key are both required")
        # test the new key against a throwaway cache before saving anything
        with tempfile.TemporaryDirectory() as t:
            env = {**os.environ, "B2_APPLICATION_KEY_ID": kid, "B2_APPLICATION_KEY": key,
                   "B2_ACCOUNT_INFO": f"{t}/info"}
            r = subprocess.run(["b2", "bucket", "list"], capture_output=True, text=True, env=env)
        if r.returncode:
            raise ValueError("B2 rejected that key: " + (r.stderr or r.stdout).strip())
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"keyId": kid, "key": key}, f)
        ACCOUNT_INFO.unlink(missing_ok=True)  # drop cached auth for the old key
        DL_AUTH.clear()
        self.send(200, {"ok": True})

    def get_api_jobs(self, q):
        self.send(200, [{k: v for k, v in j.items() if k != "proc"} for j in reversed(JOBS.values())])

    def post_api_cancel(self, q):
        j = JOBS.get(self.body().get("id"))
        if j and j["status"] == "running":
            j["status"] = "cancelled"  # stops the job before its next command (e.g. the delete half of a move)
            if j["proc"]:
                j["proc"].terminate()
        self.send(200, {"ok": True})


if __name__ == "__main__":
    print(f"B2 Browser on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
