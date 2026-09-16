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
| Packaging | PyInstaller | One bundle carrying its own Python, no runtime to install |
| macOS integration | `ctypes` against Carbon | Apple Events without pulling in pyobjc |

Pinned versions live in `requirements.txt`; test-only additions in `requirements-dev.txt`,
which is also where the packaging-only dependency on PyInstaller lives.
No CDN or remote asset may be referenced: the app must run fully offline.

## Repository layout

```
main.py             application entry point (`python main.py`)
backend/            server package
  app.py            create_app(): router + static frontend mount + error handler
  config.py         all settings, overridable via FILETOOL_* environment variables
  errors.py         domain errors (translated to HTTP 400)
  desktop.py        files the OS hands the app, and the request to stop it
  __main__.py       `python -m backend` development entry point
  api/routes.py     HTTP layer: parse, validate, shape responses
  services/         processing logic, bytes in / bytes out
    loader.py       format detection and media-type/extension mapping
    images.py       PNG <-> JPG, images -> PDF, cropping
    pdf.py          page rendering and composition (merge, reorder, remove)
frontend/           index.html, styles.css, app.js (served at /)
launcher/
  app_launcher.py   port reservation, browser opening, signal handling
  apple_events.py   macOS "Open with" and reopening: the odoc/rapp handlers and their poll
tools/              packaging, not imported by the app
  build_macos.py    builds and installs the standalone macOS app
  icon.py           draws the app icon and writes the .icns
tests/              pytest suite over services, API, launcher and packaging
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
| `GET /health` | — | `{"status": "ok", "app": bool}`; `app` is true only when the launcher is running the server, which is what makes "Quit" possible |
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
- "Quit" sits in the top bar and is shown only when `/api/health` reports that the
  app can stop itself, so it never appears during `python main.py` development. It
  confirms first, stops the app and closes its tab; where the browser will not let
  the page close itself, the page greys itself out and says the app has stopped
  rather than offering controls that can no longer reach it.
- Download happens client-side from the blob returned by the last operation.
  "Download" hands it to the browser as-is; "Save as…" next to it asks for a
  destination first, through `showSaveFilePicker` where the browser has it —
  folder and filename, with the result's own type preselected so the extension is
  kept. Browsers without the File System Access API fall back to naming the file
  and the panel says so; a cancelled dialog is not an error.

## The macOS app

`tools/build_macos.py` packages the project into `dist/FileTool.app`, a bundle
carrying its own Python so it runs on a Mac that has none:

```
.venv/bin/python -m tools.build_macos             # build dist/FileTool.app
.venv/bin/python -m tools.build_macos --install   # and put it in /Applications
```

- PyInstaller is driven through a **generated spec file**, not command line flags,
  because only a spec can hand `BUNDLE` an Info.plist. The document types are what
  put File Tool in "Open with", and they must be in the bundle before PyInstaller
  signs it rather than patched in after, which would break the signature.
- The spec, the icon and the work directory live in `build/`, the bundle in `dist/`;
  both are ignored by git, and the spec is regenerated on every build.
- The icon is **drawn by `tools/icon.py` with Pillow** and converted by macOS's own
  `iconutil`, so the artwork's source is code and no binary lives in the repository.
- `LSHandlerRank` is `Alternate` for every type: File Tool offers itself in the
  "Open with" menu and never takes a file type over from the user's default app.
- `LSUIElement` is true. The app is a server behind a browser tab and has no window
  of its own, so it must not sit in the Dock as an icon that cannot be clicked.
- Installing copies the bundle to `/Applications`, falling back to `~/Applications`
  when that is not writable, and registers it with `lsregister` so the "Open with"
  entry appears without a logout. It then unregisters the build in `dist/`, so the
  installed app is the only copy macOS knows (see below).
- `Config.PROJECT_ROOT` follows `sys._MEIPASS` when frozen, so the frontend is found
  inside the bundle exactly as it is from a checkout.

### Removing the app

Removing File Tool means dragging it out of the Applications folder. There is no
uninstaller, so each consequence of removal is handled where it arises:

- **"Open with"** — macOS itself stops offering a trashed or deleted app within
  seconds. What would keep File Tool listed is a second registered copy with the same
  bundle id, and the build in `dist/` is exactly that; installing unregisters it. A
  copy that was never registered is already the state wanted, so that is no error.
- **The server** — macOS lets a running program carry on after its bundle is moved to
  the Trash. Running from a bundle, the launcher checks every 2 seconds that the
  bundle's `Info.plist` is still where it launched from, and stops the server once it
  is not: trashed, deleted, or moved out of its folder. From a checkout nothing is
  watched.
- The app installs nothing else — no login item, launch agent or helper — so an app
  removed while closed leaves nothing behind that could start a server.

## Files opened from the Finder

macOS does not pass opened files as command line arguments. It sends the app an
`odoc` Apple Event — at launch, and **again for every later file, to the process
already running**, because LaunchServices activates the running copy instead of
starting a second one. Two consequences shape the design:

- The `odoc` handler stays installed for the life of the process, in
  `launcher/apple_events.py`, as `ctypes` calls against Carbon. PyInstaller's own
  `argv_emulation` is deliberately **off**: it would translate the launch event into
  `argv` and silently drop every file opened afterwards.
- The event queue is polled with a **zero timeout from a task on the server's event
  loop**. The queue belongs to the main thread, which is the thread uvicorn runs on,
  so this needs no second thread and changes nothing about shutdown. Off macOS, and
  if Carbon cannot be loaded, `install` returns None and the app is unchanged.
- Opening the app itself while it runs — its icon, Launchpad, Spotlight — starts
  nothing either: macOS sends the running copy a `rapp` (reopen) event. A handler for
  it shows the app the way a launch would; an app ignoring it does not respond at all.

A file that arrives has to wait for a page to ask for it, and the app has to know
whether a page is open at all, so `backend/desktop.py` holds both — **the one place
the server keeps state between requests, and never state a client sent**. It keeps
the paths the OS gave the launcher and the open pages' connections, never bytes and
never anything from an upload:

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /api/events` | — | a stream held open as long as the page is: `connected`, then a `files` line whenever files wait for this page |
| `GET /api/handoff` | — | `{files: [{token, name, size}]}`, emptying the queue |
| `GET /api/handoff/{token}` | — | that file's bytes, once |
| `POST /api/quit` | — | `{"stopping": true}`, then the server shuts down |

- These four act on the app rather than on an upload, so they require an
  `X-File-Tool` header. It is not a secret: a header no simple request may carry
  forces a browser to preflight, the app answers no preflight, and a page on another
  origin therefore cannot reach them from the user's browser.
- A token is handed out per file and works once. A request can only name a token the
  app itself generated, so these endpoints cannot be pointed at another file.
- Each open page holds **one `/api/events` connection** rather than polling. It tells
  the page the moment files arrive, and its closing tells the app the page is gone —
  at once, where a timer in a background tab is slowed to once a minute. The page
  reconnects a second after the connection drops, so a reload carries on.
- Files are announced to the **newest page only**: two pages told at once would both
  claim, leaving one with the file and one without. A page **claims only while
  idle**, since a claimed file is gone from the server and must never be taken at a
  moment it cannot be loaded. A handed-over file starts a new session, exactly like
  dropping it.
- The stream ends by itself once the app is stopping. uvicorn waits for every open
  connection before it stops, so an open page would otherwise hold the shutdown up.
- `POST /api/quit` exists because an `LSUIElement` app has no menu to quit from. The
  launcher is the only thing that knows how to stop the server, so it registers the
  callback; without it the endpoint refuses and the page hides its "Quit" button,
  which is what `app` in `/api/health` reports.

## Windows and the app's lifetime

The app has no window of its own: the page is the app. Everything below follows from
that, and applies to the macOS app only — `python main.py` opens one window and
serves until it is stopped.

- **One window per reason to show the app.** A launch, a file handed over and a
  reopen each ask for one; the launcher opens it only when no page is open and none
  is on its way, deciding and recording that under a single lock. The launch window
  counts as on its way from before the server starts, because the file a closed app
  is opened with arrives during startup — otherwise the launch and the file would
  each open a window.
- A requested window counts as on its way for **30 seconds, or until a page
  connects**. From then on only open pages count, so closing the page and opening the
  app again straight away shows it again.
- **Closing the last page stops the app** 5 seconds later, long enough for a reload to
  reconnect. Left running, the server would be invisible, and macOS would hand every
  later launch — the icon and "Open with" alike — to that hidden copy, which has no
  page to show anything in. A window on its way keeps the app alive until it arrives
  or its 30 seconds run out.
- "Quit" stops the app and then closes its tab. A browser lets a page close its own
  tab when the tab was opened for it and has no history, which is how the app opens
  it; where the browser refuses, the page says the app has stopped.
- The app also stops when it is removed (see "Removing the app"). uvicorn is given a
  **3 second graceful-shutdown timeout**, so nothing can keep a stopping app alive.

## Testing

`pytest` over every layer: services tested directly, API tested through
`fastapi.testclient`, and the launcher tested by starting `main.py` as a subprocess
and terminating it with a signal. Fixtures build PNG/JPG/PDF inputs with Pillow, so
the suite needs no binary test assets.

Packaging is tested through everything the builder *decides* — the Info.plist that
puts File Tool in "Open with", the generated spec, the icon, and where installing
puts the bundle — but the suite never runs PyInstaller, which takes minutes. Building
the app is therefore a manual step, and the tests that need macOS are skipped
elsewhere.

```
.venv/bin/python -m pytest tests -q
```

## Startup and shutdown

`main.py` is the only entry point users need:

```
.venv/bin/python main.py                       # serve and open the browser
.venv/bin/python main.py --no-browser
.venv/bin/python main.py --host … --port …
.venv/bin/python main.py report.pdf            # open files, as "Open with" does
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
