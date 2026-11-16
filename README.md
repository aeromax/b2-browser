# B2 Browser

A small web GUI that runs the official `b2` CLI. Browse buckets, upload by drag-and-drop, download, delete, and back up or restore folders with `b2 sync`.

File uploads run inside the app on `b2sdk`, the library the CLI is built on, so a drop of thousands of files doesn't start
thousands of `b2` processes. All uploads in a job share one pool of connections (the "Parallel transfers" setting): small files
go up that many at a time, and big files are split into parts that use whatever connections are free. Big files start sending
right away. The app doesn't read the whole file first to label it with a whole-file SHA-1; B2 still checks the SHA-1 of every
part. A cancelled big upload resumes from its finished parts the next time you upload the same file to the same name.

The app keeps its own B2 key and login cache in its config folder. It never uses your personal `b2 account authorize` login.

## Run locally
    pip install b2        # or: brew install b2-tools
    python3 app.py        # open http://127.0.0.1:8080, then enter a key in Settings (⚙︎)

If `python3` can't import `b2sdk` (Homebrew and pipx keep it in the CLI's own Python), the app restarts itself under the
Python that the `b2` command uses.

## Run on Unraid (Docker)
    docker compose up -d --build

Or:

    docker build -t b2-browser .
    docker run -d --name b2-browser -p 8080:8080 -e B2UI_PASSWORD=... \
      -v /mnt/user/appdata/b2-browser:/config -v /mnt/user:/data b2-browser

Open the page and enter your Key ID and application key in Settings. The app tests the key before saving it.
In the Backup/Restore dialog, local paths are paths inside the container, for example `/data/photos`.

## Getting a key
Backblaze web console → Application Keys → Add a New Application Key. It needs list, read, write, delete and share access to the buckets you want to manage. Share access lets previews stream straight from B2 with seeking; without it previews still work but are proxied through the app.

## Env vars
| Var | Default | |
|---|---|---|
| `CONFIG_DIR` | `~/.b2-browser` (`/config` in Docker) | saved key (mode 600) + b2 auth cache |
| `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY` | – | optional; a key saved in Settings takes priority |
| `B2UI_PASSWORD` | – | HTTP basic auth (any username works). Required unless `HOST` is loopback; the app won't start without it. |
| `B2UI_TEMP_DIR` | system temp | Where uploads are spooled before going to B2 (one full copy per in-flight file, up to 4). Point it at a volume with room for your largest files. Leftovers from a crash are deleted at startup. |
| `DATA_ROOT` | – (`/data` in Docker) | Backup/Restore local paths must be inside this folder. |
| `HOST`, `PORT` | `127.0.0.1`, `8080` | `0.0.0.0` in Docker |
