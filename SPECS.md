# Architecture & Standards

Binding technical decisions for File Tool. Keep this file current with the code.

## Stack

| Concern | Choice | Reason |
| --- | --- | --- |
| Server | FastAPI + uvicorn | Multipart uploads, static hosting and typed handlers in one process |
| Images | Pillow | PNG/JPG conversion and image-to-PDF without external binaries |
| PDF editing | pypdf | Lossless page removal, pure Python, permissive licence |
| PDF rendering | pypdfium2 | Page rasterisation for previews, wheels for all target platforms, no poppler |
| Frontend | Plain HTML/CSS/JS | No build step, works from a PyInstaller bundle as static files |

Pinned versions live in `requirements.txt`; test-only additions in `requirements-dev.txt`.
No CDN or remote asset may be referenced: the app must run fully offline.

## Repository layout

```
main.py             application entry point (`python main.py`)
backend/            server package
  app.py            create_app(): router + static frontend mount + error handler
  config.py         all settings, overridable via FILETOOL_* environment variables
  errors.py         domain errors (translated to HTTP 400)
  __main__.py       `python -m backend` development entry point
  api/routes.py     HTTP layer: parse, validate, shape responses
  services/         processing logic, bytes in / bytes out
    loader.py       format detection and media-type/extension mapping
    images.py       PNG <-> JPG, image -> PDF
    pdf.py          page rendering and page removal
frontend/           index.html, styles.css, app.js (served at /)
launcher/
  app_launcher.py   port reservation, browser opening, signal handling
tests/              pytest suite over services and API
```

## Layering rules

- `services/` never import FastAPI and never touch the filesystem or global state;
  they take and return `bytes`.
- `api/routes.py` holds no processing logic — it reads the upload, calls a service
  and shapes the response.
- The frontend performs no file processing; every operation is an API call.

## API contract

All endpoints are prefixed `/api`. Uploads use `multipart/form-data` with the field
name `file`. Requests are stateless: the client sends the file it wants to act on
with every request, and the server stores nothing.

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /health` | — | `{"status": "ok"}` |
| `POST /load` | `file` | `{format, name, size, targets[], pages[]}`; `pages` holds `{index, width, height, image}` with `image` a PNG data URL (empty for images) |
| `POST /convert` | `file`, `target` (`png`\|`jpg`\|`pdf`) | Converted file as a binary download |
| `POST /pdf/remove-pages` | `file`, repeated `pages` (zero-based indices) | Edited PDF as a binary download |

Binary responses carry the correct `Content-Type` and
`Content-Disposition: attachment; filename="…"`; the filename is derived from the
upload, restricted to printable ASCII.

Errors: any `FileToolError` becomes `400 {"error": "<message>"}`. Messages are written
for the user and are shown verbatim in the UI. Unexpected exceptions stay 500s.

## Input handling

- Accepted inputs: PDF, PNG, JPG.
- The format is detected from magic bytes, never from the filename or the browser's
  content type.
- Uploads are held in memory only and capped by `Config.MAX_UPLOAD_BYTES` (100 MB).
- Conversion targets are defined once, in `images.CONVERSION_TARGETS`, and the
  frontend renders whatever `/load` reports — options are never hardcoded in the UI.
- A page-removal request must leave at least one page.

## Frontend conventions

- One panel per stage: input, PDF pages or convert options, result.
- PDFs show the scrollable page list; images show the conversion options. Never both.
- `−` marks a page for removal (toggle, no immediate request); "Apply changes" sends
  one request with all marked indices.
- The result of an edit becomes the working file, so operations can be stacked.
- Download happens client-side from the blob returned by the last operation.

## Testing

`pytest` over every layer: services tested directly, API tested through
`fastapi.testclient`, and the launcher tested by starting `main.py` as a subprocess
and terminating it with a signal. Fixtures build PNG/JPG/PDF inputs with Pillow, so
the suite needs no binary test assets.

```
.venv/bin/python -m pytest tests -q
```

## Startup and shutdown

`main.py` is the only entry point users need:

```
.venv/bin/python main.py                       # serve and open the browser
.venv/bin/python main.py --no-browser
.venv/bin/python main.py --host … --port …
.venv/bin/python -m backend                    # server only, for development
```

Rules the launcher follows:

- **One process.** uvicorn serves the API and the frontend; there is no second
  process or server thread that could outlive the launcher.
- **The port is bound before the server starts** (`reserve_socket`), so the URL
  printed and handed to the browser is the port actually in use. If the configured
  port is taken, a free one is used and reported instead of failing.
- **The browser is opened from a daemon thread** that waits for the server to accept
  connections and gives up after 15 seconds with a printed URL.
- **SIGINT and SIGTERM shut down gracefully and exit 0.** The launcher installs its
  own handlers first: uvicorn restores them and re-raises the signal after its
  graceful shutdown, and those handlers make that re-raise harmless instead of
  killing the process mid-cleanup. The listening socket is closed in a `finally`.

Host and port come from `Config`; the server binds `127.0.0.1` by default so the app
is not exposed to the network.
