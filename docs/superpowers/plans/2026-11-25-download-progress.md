# Download Progress Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show live progress (per-file bar, overall bar, speed, time left, Cancel) for downloads, which today are bare `<a download>` clicks with no feedback.

**Architecture:** The browser/Electron keeps doing the real download. `/api/download` takes an `id` and `size`, sends `Content-Length`, counts bytes written, and records them in an in-memory registry. The page polls `/api/downloads` and draws a panel with the existing `xferHTML` and `meter`. Cancel kills the `b2 file cat` process.

**Tech Stack:** Python stdlib `http.server` (`app.py`), vanilla JS in `index.html`, `unittest` for server tests (no test suite exists yet; add `tests/test_downloads.py`).

**Spec:** `docs/superpowers/specs/2026-11-25-download-progress-design.md`

## Global Constraints

- No buffering of file contents in memory or in the page; saving stays native.
- Don't touch the upload panel `#xfer`, the Activity popover, previews (`/api/preview`), or `mac/`.
- Folder downloads remain unsupported.
- `id` and `size` are optional on `/api/download`, so existing links (drag-out `DownloadURL`) behave as before.
- Match surrounding style: terse Python, one-line comments, no new dependencies.

## Review Focus

- `size` missing, negative, or non-numeric: download works, with no `Content-Length` and no registry entry for a bad size; never a 500.
- Browser disconnects mid-download (`BrokenPipeError`): entry ends `cancelled`/`failed`, `b2 file cat` is killed, and nothing leaks.
- Cancel of an unknown or already-finished id: returns ok and changes nothing.
- Same `id` reused (Quick Look link clicked twice): the second download replaces the first entry instead of crashing.
- Finished entries are pruned so the registry doesn't grow forever.

---

### Task 1: Server — download registry, counted stream, list and cancel

**Files:**
- Modify: `app.py` (near `JOBS` at line 38; `stream()` at 434; `get_api_download` at 449; add routes after `post_api_cancel` at 647)
- Create: `tests/test_downloads.py`

**Interfaces:**
- Produces: `DOWNLOADS: dict[str, dict]` with entries `{"id", "name", "size", "sent", "status", "proc", "started", "ended"}`; status is one of `running|done|cancelled|failed`.
- Produces: `GET /api/download?bucket&path[&id&size]`. `GET /api/downloads` returns `[{id, name, size, sent, status, elapsed}]`, newest first, with no `proc`. `POST /api/download_cancel` takes body `{"id": str}` and returns `{"ok": true}`.

- [ ] **Step 1: Write failing tests** in `tests/test_downloads.py`. The fixture starts `ThreadingHTTPServer(("127.0.0.1", 0), app.H)` in a thread. It patches `app.b2_env` to return an env whose `PATH` begins with a temp dir holding an executable fake `b2` shell script. The script writes 3 MiB of zeros and exits 0; a second variant sleeps 30 s after writing 1 MiB. Tests, using `urllib.request`:
  - `test_download_sends_content_length_and_tracks`: GET with `id=d1&size=3145728` returns header `Content-Length: 3145728` and a 3145728-byte body. Then `/api/downloads` has `d1` with `status == "done"` and `sent == 3145728`.
  - `test_download_without_id_unchanged`: GET with no `id` has no `Content-Length` header and `/api/downloads` is `[]`.
  - `test_bad_size_ignored`: `size=abc` and `size=-5` both return 200 with no `Content-Length` and no 500.
  - `test_cancel_kills_process`: start the slow variant in a thread; once `sent > 0`, POST `/api/download_cancel {"id": "d2"}`. Assert the entry becomes `cancelled` within 5 s and the fake process is gone.
  - `test_cancel_unknown_id_ok`: returns `{"ok": true}`.
  - `test_reused_id_replaces_entry`: two sequential downloads with the same id leave one entry.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_downloads -v`
Expected: FAIL (no `Content-Length`, `/api/downloads` returns 404).

- [ ] **Step 3: Implement.** In `app.py`:
  - Add `DOWNLOADS = {}` beside `JOBS`.
  - Add `def track_download(id, name, size) -> dict`. It creates and registers the entry, replacing any entry with the same id, and prunes entries that ended more than 60 s ago.
  - Extend `stream(self, bucket, path, ctype, disposition, limit=None, dl=None)`. `dl` is the entry, or `None` for previews. When `dl` is set, send `Content-Length` (valid only when `dl["size"]` is a non-negative int), set `dl["proc"]`, and add each written chunk's length to `dl["sent"]`.
  - On normal end set `done`. If `dl["status"]` is already `cancelled`, leave it. On `BrokenPipeError`/`ConnectionResetError`, or if the stream ends before `size`, set `failed`. Set `ended` and `proc = None` in the `finally`.
  - `get_api_download` reads `q.get("id")` and `q.get("size")`. It parses the size with a try/except into an int, treating anything non-numeric or negative as unknown. It registers an entry only when an `id` is given (name is the basename of the path).
  - Add `get_api_downloads(self, q)`, using the same server-side `elapsed` approach as `get_api_jobs`. Add `post_api_download_cancel(self, q)`. It marks a running entry `cancelled` first, then terminates its proc, so `stream()` doesn't overwrite the status.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_downloads -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_downloads.py
git commit -m "Track downloads on the server: Content-Length, byte count, list and cancel"
```

---

### Task 2: Page — download panel, tracked links, status-bar summary

**Files:**
- Modify: `index.html` (CSS near `#xfer` at line ~214; markup beside `#xfer` at line ~294; `downloadURL` at 386; `quickLook` at 544; `download` at 727)

**Interfaces:**
- Consumes: Task 1's `/api/downloads` (entries with `id, name, size, sent, status, elapsed`) and `POST /api/download_cancel {id}`.
- Produces: `trackedURL(it: {name, size}) -> string`, which is `downloadURL(it)` plus `&id=<unique>&size=<size>`. `pollDownloads(): Promise<void>`. Element `#dl` (panel) with `#dlTitle`, `#dlBody`, `#dlCancel`.

- [ ] **Step 1: Markup and CSS.** Add `<div id="dl" hidden><div class="xh"><b id="dlTitle"></b><button class="btn" id="dlCancel">Cancel all</button></div><div id="dlBody"></div></div>` beside `#xfer`. Reuse the `#xfer` rules by extending its selectors to `#xfer, #dl`. Offset `#dl` so it never overlaps a visible `#xfer`: use `bottom: 40px` and move it up with `#xfer:not([hidden]) ~ #dl`.

- [ ] **Step 2: `trackedURL` and callers.** Define `trackedURL` next to `downloadURL`. The id is `Date.now().toString(36) + Math.random().toString(36).slice(2, 6)`. `download(list)` uses it for each link and calls `pollDownloads()` after the first click. In `quickLook`, keep `href = downloadURL(it)`, and add a click handler on `#qlDl` that sets `href = trackedURL(it)` before the default action, then calls `pollDownloads()`. Leave the `DownloadURL` drag-out line unchanged.

- [ ] **Step 3: `pollDownloads()`.** Fetch `/api/downloads` with `api(...).catch(() => [])`. Keep a `dlRates` Map of `meter()` per id, like `jobRates`. Running entries are the active set. Draw with `xferHTML({ files: running.map(d => ({ name: d.name, phase: '', frac: d.size ? d.sent / d.size : null })), done: Σsent, total: Σsize, filesDone: finished-in-this-batch, filesTotal: batch size, speed: Σ per-id rate(d.sent, d.elapsed), elapsed: max(d.elapsed) })`. Set the title to `Downloading N file(s)`. Show `#dl` only while something is running. When it stops, hide it and clear `progress(null)`. While active, call `progress(title, frac)` for the status-bar summary. Reschedule with `setTimeout(pollDownloads, 500)` while any entry is running. When an entry newly turns `failed`, call `showErr("Couldn’t download <name>.")`. A `cancelled` entry stays silent.
  - Don't let `progress()` clobber an in-flight upload's status line. If `uploading` is already true because of an upload or delete, skip the summary.

- [ ] **Step 4: Cancel.** `#dlCancel` posts `/api/download_cancel` for every running id, then polls.

- [ ] **Step 5: Manual verification.**
  Run: `python3 app.py` (or `cd mac && npm start`), open the app, and download a file larger than about 50 MB.
  Expected:
  - The panel appears with the file name, a moving bar, speed and time left, and the status bar shows "Downloading 1 file".
  - Cancel stops the transfer and the panel disappears.
  - A multi-file selection shows the "files left" count.
  - Quick Look's Download link works twice in a row.
  - An upload running at the same time still shows its own panel and status line.
  - The browser's native bar shows a percentage.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "Show a progress panel for downloads"
```

---

## Self-review

- **Spec coverage:** the registry, `Content-Length`, list and cancel endpoints, panel, status-bar summary, Quick Look link, and unchanged drag-out and previews are covered by Tasks 1 and 2. Pruning and bad `size` are covered in the Task 1 tests.
- **Types:** the entry fields (`id, name, size, sent, status, elapsed`) and the names `trackedURL`, `pollDownloads`, `/api/download_cancel` match across both tasks.
