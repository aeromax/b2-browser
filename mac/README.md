# B2 Browser for Mac

A native shell (Electron) around the same app. The difference: it knows the real path of every file you drop,
so `b2` uploads each one **where it is stored**. Nothing is copied to temp, however big the file.

- Drop any mix of files and folders. Folders go through `b2 sync` (parallel, suits tens of thousands of small files);
  loose files are uploaded up to 4 at a time. The whole drop is one job with overall progress; one failed file
  doesn't stop the rest, and failures are listed in the job log.
- "Upload files…" / "Upload a folder…" open the macOS file picker.
- Backup/restore, browsing, preview, and the rest work as in the web version.

## Requirements
`python3` and the `b2` CLI (`brew install b2-tools`). The app finds them in `/opt/homebrew/bin` or `/usr/local/bin`.

## Run / build
    cd mac && npm install
    npm start          # run it
    npm run dist       # builds dist/mac-arm64/B2 Browser.app (unsigned: right-click > Open the first time)

Keys are saved in `~/Library/Application Support/B2 Browser/config`.
