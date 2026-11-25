# Download progress panel — design

## Intent
Downloads currently show nothing: `download()` clicks a hidden `<a download>` and the browser/Electron does the rest, so the page never sees progress. Uploads have a good panel (`#xfer`). Give downloads the same kind of feedback.

## Goals
- A download panel with a bar per file, overall bar, speed, time left, and Cancel, reusing `xferHTML`, `meter`, and the `#xfer` styling.
- Works in browsers and the Mac app with no Electron changes.
- Browser's own download bar shows a real percentage (needs `Content-Length`).

## Non-goals
- No merging of uploads / downloads / jobs into one indicator (option 2 chosen). Existing `#xfer`, `#stat` and Activity stay as they are.
- No folder downloads (not supported today).
- No change to previews (`/api/preview`) beyond keeping them working.

## Anti-goals
- Don't buffer files in memory or in the page; saving stays native.

## Approaches considered
- A. Page `fetch`es and counts bytes: needs in-memory Blob or Chrome-only File System Access API. Rejected.
- **B. Native download, server reports progress (chosen).**
- C. Electron `will-download` + IPC: Mac app only. Rejected.

## Design (B)
Server (`app.py`):
- `DOWNLOADS = {}` registry: id -> `{id, name, size, sent, status, proc, started, ended}`.
- `/api/download` takes `id` and `size` query params from the page. It sends `Content-Length: size` when given, counts bytes written in `stream()`, and sets status `done` / `cancelled` / `failed`. Previews are unaffected (no id, no length).
- `GET /api/downloads` returns the entries; finished ones are dropped after a short time.
- `POST /api/download_cancel` kills the `b2 file cat` process.
- Validate that `size` is a non-negative int. If the real stream is shorter than `Content-Length`, the browser reports the failure and the entry is marked `failed`.

Page (`index.html`):
- `download(list)` assigns an id per file and adds `&id=…&size=…` to `downloadURL` for the link.
- A new `#dlpanel`, styled like `#xfer` and placed above it, polls `/api/downloads` while any are active. It draws with `xferHTML` (per-file bars, overall bar, speed via `meter`, time left, files left) and a Cancel button.
- It hides itself when nothing is active. A failed or cancelled download shows a line in `showErr`.
- The status bar `#stat` gets a one-line "Downloading N files" summary with a bar, via the existing `progress()` helper, so there is a quiet indicator when the panel is closed.

## Left to the builder
- Poll interval (about 500 ms) and how long finished entries linger.
- Quick Look's Download link also gets an id and size.
- Exact placement and wording of the panel.

## Notes
- Progress counts bytes handed to the browser, so it can run slightly ahead of what is saved to disk.
- Dragging a file out to the desktop (`DownloadURL`) is left as is, with no progress.
