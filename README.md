# B2 Browser

Node.js proxy and UI for Backblaze B2 uploads/downloads.

## Running with Docker

1. Build the image:
   ```bash
   docker build -t b2-browser .
   ```
2. Run the container (replace the credential placeholders):
   ```bash
   docker run \
     --name b2-browser \
     -p 3000:3000 \
     -e B2_ID=your-application-key-id \
     -e B2_KEY=your-application-key \
     -d b2-browser
   ```
   Optional: add `-e PORT=8080 -p 8080:8080` if you want the app to listen on a different port in the container.

### Unraid notes

- In the Docker template, set environment variables `B2_ID` and `B2_KEY` (and `PORT` if you want a custom port).
- Map the container port (`3000` by default) to whichever host port you need.
- No persistent volumes are required; the app is stateless aside from Backblaze.

### Health check

The service exposes `GET /api/health`. Example:
```bash
docker exec b2-browser curl -sf http://localhost:3000/api/health
```
This returns `{ "ok": true }` when the server is accepting requests.

## Local development (non-Docker)

```bash
npm install
npm run dev
```

Create a `.env` file with `B2_ID` and `B2_KEY` when running locally.
