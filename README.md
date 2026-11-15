# B2 Browser

A small web GUI that runs the official `b2` CLI. Browse buckets, upload by drag-and-drop, download, delete, and back up or restore folders with `b2 sync`.

The app keeps its own B2 key and login cache in its config folder. It never uses your personal `b2 account authorize` login.

## Run locally
    pip install b2
    python3 app.py        # open http://127.0.0.1:8080, then enter a key in Settings (⚙︎)

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
| `DATA_ROOT` | – (`/data` in Docker) | Backup/Restore local paths must be inside this folder. |
| `HOST`, `PORT` | `127.0.0.1`, `8080` | `0.0.0.0` in Docker |
