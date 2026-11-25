import json, os, stat, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app

FAST = "head -c 3145728 /dev/zero\n"
SLOW = "echo $$ > \"$PIDFILE\"\nhead -c 1048576 /dev/zero\nexec sleep 30\n"


class Base(unittest.TestCase):
    script = FAST

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        b = Path(self.tmp.name, "b2")
        b.write_text("#!/bin/sh\n" + self.script)
        b.chmod(b.stat().st_mode | stat.S_IEXEC)
        self.pidfile = str(Path(self.tmp.name, "pid"))
        env = {**os.environ, "PATH": self.tmp.name + os.pathsep + os.environ["PATH"], "PIDFILE": self.pidfile}
        self.orig, app.b2_env = app.b2_env, lambda: env
        app.DOWNLOADS.clear()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        app.b2_env = self.orig
        self.tmp.cleanup()

    def get(self, path):
        return urllib.request.urlopen(self.base + path)

    def list(self):
        return json.load(self.get("/api/downloads"))

    def post(self, path, body):
        r = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(r))


class Downloads(Base):
    def test_download_sends_content_length_and_tracks(self):
        r = self.get("/api/download?bucket=b&path=a/f.bin&id=d1&size=3145728")
        self.assertEqual(r.headers["Content-Length"], "3145728")
        self.assertEqual(len(r.read()), 3145728)
        for _ in range(50):  # the handler finishes just after the client has read everything
            d = {e["id"]: e for e in self.list()}
            if d["d1"]["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(d["d1"]["status"], "done")
        self.assertEqual(d["d1"]["sent"], 3145728)
        self.assertEqual(d["d1"]["name"], "f.bin")
        self.assertNotIn("proc", d["d1"])

    def test_download_without_id_unchanged(self):
        r = self.get("/api/download?bucket=b&path=f.bin")
        self.assertIsNone(r.headers["Content-Length"])
        r.read()
        self.assertEqual(self.list(), [])

    def test_bad_size_ignored(self):
        for s in ("abc", "-5"):
            r = self.get(f"/api/download?bucket=b&path=f.bin&id=x{s}&size={s}")
            self.assertEqual(r.status, 200)
            self.assertIsNone(r.headers["Content-Length"])
            r.read()

    def test_cancel_unknown_id_ok(self):
        self.assertEqual(self.post("/api/download_cancel", {"id": "nope"}), {"ok": True})

    def test_reused_id_replaces_entry(self):
        for _ in range(2):
            self.get("/api/download?bucket=b&path=f.bin&id=same&size=3145728").read()
        self.assertEqual([e["id"] for e in self.list()], ["same"])


class Cancel(Base):
    script = SLOW

    def test_cancel_kills_process(self):
        def run():
            try:
                self.get("/api/download?bucket=b&path=f.bin&id=d2&size=3145728").read()
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()
        for _ in range(50):
            if any(e["sent"] > 0 for e in self.list()):
                break
            time.sleep(0.1)
        self.assertEqual(self.post("/api/download_cancel", {"id": "d2"}), {"ok": True})
        for _ in range(50):
            if self.list()[0]["status"] == "cancelled":
                break
            time.sleep(0.1)
        self.assertEqual(self.list()[0]["status"], "cancelled")
        pid = int(Path(self.pidfile).read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            self.fail("fake b2 process still alive")


if __name__ == "__main__":
    unittest.main()
