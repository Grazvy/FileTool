"""Start the local server, open the browser, and stop cleanly on termination.

Everything runs in one process: uvicorn serves both the API and the frontend, and
its own signal handling turns SIGINT (Ctrl+C) and SIGTERM into a graceful
shutdown, so no server thread or child process can outlive the launcher.

Running as the macOS app, this is also where the app's life is decided: it opens
one window for each reason to show the user something, takes the files the OS
hands over through "Open with", and stops once its page is closed, it is removed,
or the page asks it to quit.
"""

import argparse
import asyncio
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from backend import desktop
from backend.app import create_app
from backend.config import IS_BUNDLED, Config
from launcher import apple_events

BROWSER_TIMEOUT_SECONDS = 15.0

# A window asked for this recently may still be starting the browser and loading
# the page. Meanwhile nothing opens a second one, and the app does not stop for
# want of a page before that one had its chance to connect.
WINDOW_GRACE_SECONDS = 30.0

# How long the app outlives its last page: long enough for a reload to reconnect,
# short enough that closing the tab closes the app.
PAGE_GRACE_SECONDS = 5.0
PAGE_POLL_SECONDS = 1.0

# How often the app checks that it is still installed. Removing it from the
# Applications folder while it runs must not leave a server behind.
REMOVAL_POLL_SECONDS = 2.0

# uvicorn waits for every open connection before it stops. Pages end theirs when
# the app stops, and this makes sure nothing else can keep a stopping app alive.
SHUTDOWN_TIMEOUT_SECONDS = 3

_window_requested: float | None = None
_window_lock = threading.Lock()


def reserve_socket(host: str, port: int) -> socket.socket:
    """Bind the requested port, falling back to a free one if it is taken.

    Binding before uvicorn starts means the real port is known in advance, so the
    browser is never sent to a port the server did not get.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.bind((host, 0))
        print(f"Port {port} is already in use, using port {sock.getsockname()[1]} instead.")
    return sock


def open_browser_when_ready(server: uvicorn.Server, url: str) -> threading.Thread:
    """Open the browser once the server accepts connections.

    The window counts as on its way from this call, before the server has even
    started: a file macOS hands over during the launch goes to this window rather
    than opening a second one. Runs on a daemon thread so a browser that never
    opens cannot hold up exit.
    """
    with _window_lock:
        note_window_requested()

    def wait_and_open() -> None:
        deadline = time.monotonic() + BROWSER_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if server.should_exit:
                return
            if server.started:
                webbrowser.open(url)
                return
            time.sleep(0.1)
        print(f"The server took too long to start. Open {url} manually.")

    thread = threading.Thread(target=wait_and_open, name="open-browser", daemon=True)
    thread.start()
    return thread


def note_window_requested(now: float | None = None) -> None:
    global _window_requested
    _window_requested = time.monotonic() if now is None else now


def window_is_coming(now: float | None = None) -> bool:
    """Whether a page is open, or a window was asked for and has not arrived yet.

    A window has arrived once a page connects after it was asked for. From then
    on only that page counts, so closing it closes the app, and opening the app
    again straight away shows it again instead of waiting out the grace period.
    """
    if desktop.pages_connected():
        return True
    if _window_requested is None:
        return False
    joined = desktop.last_page_joined()
    if joined is not None and joined >= _window_requested:
        return False
    current = time.monotonic() if now is None else now
    return current - _window_requested < WINDOW_GRACE_SECONDS


def show_app(url: str) -> bool:
    """Open a window on the app, unless a page is open or one is already on its way.

    Checked and marked under one lock, so two reasons arriving together still
    open a single window. Returns whether a window was opened.
    """
    with _window_lock:
        if window_is_coming():
            return False
        note_window_requested()
    webbrowser.open(url)
    return True


def hand_over(paths: list[Path], url: str) -> None:
    """Take files the OS opened with the app and get them in front of the user.

    An open page is told at once and loads them; a window is opened only when
    there is no page to tell and none on its way.
    """
    if desktop.offer(paths):
        show_app(url)


def watch_opened_files(app, url: str) -> apple_events.Watcher | None:
    """Listen for "Open with" and reopening while the app runs, from the server's loop.

    The Carbon event queue belongs to the main thread, which is where uvicorn
    runs its loop, so the poll is a task on that loop rather than a thread.
    """
    watcher = apple_events.install(
        on_files=lambda paths: hand_over(paths, url),
        on_reopen=lambda: show_app(url),
    )
    if watcher is None:
        return None

    async def start_watching() -> None:
        asyncio.create_task(watcher.run())

    app.router.on_startup.append(start_watching)
    app.router.on_shutdown.append(watcher.stop)
    return watcher


def running_bundle(executable: str | None = None, bundled: bool | None = None) -> Path | None:
    """The .app this process runs from, or None when it does not run from one."""
    if not (IS_BUNDLED if bundled is None else bundled):
        return None
    for parent in Path(executable or sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def is_removed(bundle: Path) -> bool:
    """Whether the app is gone from where it was launched: trashed, deleted or moved."""
    return not (bundle / "Contents" / "Info.plist").is_file()


def watch_for_removal(app, server: uvicorn.Server, bundle: Path | None) -> None:
    """Stop the server once the app it belongs to is removed.

    macOS lets a running program carry on after its bundle is dragged to the
    Trash, so without this the server would outlive the app the user removed.
    Moving the app out of its folder counts too: it is no longer installed there,
    and the next launch starts from wherever it went.
    """
    if bundle is None:
        return

    async def check() -> None:
        while not server.should_exit:
            if is_removed(bundle):
                print(f"{bundle.name} was removed, stopping File Tool.")
                server.should_exit = True
                return
            await asyncio.sleep(REMOVAL_POLL_SECONDS)

    async def start_checking() -> None:
        asyncio.create_task(check())

    app.router.on_startup.append(start_checking)


def is_unattended(now: float | None = None) -> bool:
    """Whether the app has no page and none on its way: its window was closed."""
    return not window_is_coming(now) and desktop.seconds_without_page(now) >= PAGE_GRACE_SECONDS


def stop_when_closed(app, server: uvicorn.Server, bundle: Path | None) -> None:
    """Stop the server once its last page is closed.

    The app has no window of its own: the page is the app. If closing it left the
    server running unseen, macOS would hand every later launch — the app's icon,
    "Open with" — to that hidden copy instead of starting a new one. Only the
    macOS app does this; `python main.py` serves until it is stopped.
    """
    if bundle is None:
        return

    async def check() -> None:
        while not server.should_exit:
            if is_unattended():
                print("The last File Tool page was closed, stopping.")
                server.should_exit = True
                return
            await asyncio.sleep(PAGE_POLL_SECONDS)

    async def start_checking() -> None:
        asyncio.create_task(check())

    app.router.on_startup.append(start_checking)


def install_shutdown_handlers(server: uvicorn.Server) -> None:
    """Make a terminating signal end in a normal exit.

    uvicorn shuts down gracefully on SIGINT/SIGTERM, but afterwards it restores
    the previous handlers and re-raises the signal it caught. With the default
    handlers in place that kills the process before the launcher can finish, so
    the previous handler is one of ours: it only asks the server to stop, which
    is already done by then, and the launcher exits normally.
    """

    def request_stop(_signum: int, _frame) -> None:
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, request_stop)
        except ValueError:  # not the main thread; uvicorn then handles nothing
            return


def run(
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = True,
    files: list[str] | None = None,
) -> int:
    """Run the app until it is terminated. Returns the process exit code."""
    global _window_requested
    host = host or Config.HOST
    port = Config.PORT if port is None else port

    if not Config.FRONTEND_DIR.is_dir():
        print(f"Frontend files not found at {Config.FRONTEND_DIR}.", file=sys.stderr)
        return 1

    sock = reserve_socket(host, port)
    url = f"http://{host}:{sock.getsockname()[1]}"
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            timeout_graceful_shutdown=SHUTDOWN_TIMEOUT_SECONDS,
        )
    )

    desktop.reset()
    _window_requested = None
    # Running under the launcher is what makes "Quit" in the page possible: it is
    # the only place that knows how to stop the server.
    desktop.on_quit(lambda: setattr(server, "should_exit", True))
    desktop.on_stopping(lambda: server.should_exit)

    bundle = running_bundle()
    watch_opened_files(app, url)
    watch_for_removal(app, server, bundle)
    stop_when_closed(app, server, bundle)
    # macOS sends opened files as events rather than arguments, but a file named
    # on the command line means the same thing and is waiting before the page is.
    desktop.offer(files or [])

    install_shutdown_handlers(server)
    if open_browser:
        open_browser_when_ready(server, url)

    print(f"File Tool is running at {url} — press Ctrl+C to stop.")
    try:
        # Serves until a terminating signal arrives, then returns once the
        # server has finished shutting down.
        server.run(sockets=[sock])
    finally:
        sock.close()
    print("File Tool stopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="File Tool", description="Run File Tool locally.")
    parser.add_argument("--host", default=Config.HOST, help="Interface to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=Config.PORT, help="Port to bind (default: %(default)s)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    parser.add_argument("files", nargs="*", help="Files to open in the app")
    args = parser.parse_args(argv)
    return run(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        files=args.files,
    )
