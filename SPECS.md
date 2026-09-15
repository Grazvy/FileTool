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
    images.py       PNG <-> JPG, images -> PDF, cropping
    pdf.py          page rendering and composition (merge, reorder, remove)
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
name `file`, repeated once per file where several are allowed. Requests are
stateless: the client sends every file it wants to act on with every request, and
the server stores nothing.

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /health` | — | `{"status": "ok"}` |
| `POST /load` | one `file` | `{format, name, size, targets[], multi_targets[], pages[]}`; `pages` holds `{index, width, height, image}` with `image` a PNG data URL (empty for images) |
| `POST /convert` | one or more `file`, `target` (`png`\|`jpg`\|`pdf`) | Converted file as a binary download; several files are laid out as the pages of one document, in upload order, and only a `multi_targets` target accepts them |
| `POST /image/crop` | one `file`, `left`, `top`, `right`, `bottom` | The cut out part of the image, in the format it came in, as a binary download |
| `POST /pdf/compose` | one or more `file`, repeated `pages` as `document:page` (both zero-based) | A PDF holding exactly those pages, in that order, as a binary download |

`/pdf/compose` is the single page-editing endpoint: the order of `pages` is the
order of the result, pages left out are dropped, and references into several
documents merge them. All uploads must be PDFs.

`/image/crop` takes its box as fractions of the image (`0`–`1`, left < right and
top < bottom), never as pixels: the client works from what it displays and the
server owns the original's size. Rounding never collapses the box — at least one
pixel is kept in each direction.

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
- Several files may be worked on at once, but they must all have the same format;
  mixing is rejected.
- Conversion targets are defined once, in `images.CONVERSION_TARGETS`, and those
  able to hold several images at once in `images.MULTI_TARGETS`. The frontend
  renders whatever `/load` reports — options are never hardcoded in the UI.
- A composed PDF must keep at least one page.
- Cropping is an image operation: PDFs are rejected, and the output keeps the
  input's format rather than converting.

## Frontend conventions

- One panel per stage: input, PDF pages or convert options, result.
- PDFs show the scrollable page list; images show the conversion options. Never both.
- The editing state is two values: `state.documents`, every uploaded file of the
  current format in upload order, and `state.order`, the sequence being built as
  `{doc, page}` references into them. Removing drops a reference, moving swaps two,
  adding a file appends its pages. Nothing is sent until the panel's button is
  pressed, and the whole order goes in that one request.
- The dropzone starts a new session; "+ Add file" in the input panel extends the
  current one with more files of the same format. A different format is refused
  with a message naming both.
- `−`, `↑` and `↓` sit on every card, in the panel list and in the expanded
  preview. Labels number the current order, so moving a page renumbers what
  follows; with several documents loaded each card also names its source file.
  The last remaining entry cannot be removed, so a request can never empty the
  document.
- The primary button says what it will do: "Apply changes" for one document,
  "Merge & apply changes" (PDF) or "Merge & convert" (images) for several. It is
  enabled only when the order differs from what the backend last produced.
- One image keeps the plain preview; several switch to the same card list, and the
  conversion targets narrow to `multi_targets`, so ordering the files orders the
  pages of the merged document.
- A single image carries a crop frame over its preview, as a third editing state:
  `state.crop`, the selection in fractions of the image, or `null` for the whole
  image. Dragging on the image draws a frame, dragging the frame moves it and its
  eight handles resize it; a click, or a selection too small to mean anything,
  clears it. The frame is laid out in percentages inside a `.crop-stage` wrapped
  tightly around the image, so it needs no measuring and no resize handling, and
  every overlay showing that image — the panel and the expanded preview — paints
  the same state, so a drag in one moves both. "Crop", next to "Convert", is shown
  only for a single image and enabled only while the frame would cut something off;
  its result becomes the working file, like an applied PDF change.
- Each preview panel carries an "Expand" button top right that opens the same
  content, larger, in a modal `<dialog>` with its own scroll area. It closes on
  Escape, the backdrop or "Close". Pages are never upscaled past the resolution
  `Config.PREVIEW_DPI` rendered them at.
- Cards are built once per `doc:page` and reused across renders, so reordering
  moves nodes instead of re-decoding previews. The caches are dropped whenever the
  documents behind them change.
- Undo/redo sit next to the primary button and in the popup header (`ctrl`/`cmd+z`,
  add `shift` to redo). A history step is a snapshot of the whole editable state —
  documents, order, crop selection, result — pushed when files are added, when a
  page is removed or moved, at the end of a drag that changed the crop frame, and
  when a change is applied. Undo therefore also steps back over an apply
  or a merge, restoring the previous documents together with their pending edits,
  and the result panel follows the step. A new upload starts a fresh history.
- The result of an edit becomes the working file, so operations can be stacked.
- Download happens client-side from the blob returned by the last operation.
  "Download" hands it to the browser as-is; "Save as…" next to it asks for a
  destination first, through `showSaveFilePicker` where the browser has it —
  folder and filename, with the result's own type preselected so the extension is
  kept. Browsers without the File System Access API fall back to naming the file
  and the panel says so; a cancelled dialog is not an error.

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
