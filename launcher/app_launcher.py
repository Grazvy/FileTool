"""Start the local server, open the browser, and stop cleanly on termination.

Everything runs in one process: uvicorn serves both the API and the frontend, and
its own signal handling turns SIGINT (Ctrl+C) and SIGTERM into a graceful
shutdown, so no server thread or child process can outlive the launcher.
"""

import argparse
import signal
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from backend.app import create_app
from backend.config import Config

BROWSER_TIMEOUT_SECONDS = 15.0


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

    Runs on a daemon thread so a browser that never opens cannot hold up exit.
    """

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


def run(host: str | None = None, port: int | None = None, open_browser: bool = True) -> int:
    """Run the app until it is terminated. Returns the process exit code."""
    host = host or Config.HOST
    port = Config.PORT if port is None else port

    if not Config.FRONTEND_DIR.is_dir():
        print(f"Frontend files not found at {Config.FRONTEND_DIR}.", file=sys.stderr)
        return 1

    sock = reserve_socket(host, port)
    url = f"http://{host}:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, log_level="info"))

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
    args = parser.parse_args(argv)
    return run(host=args.host, port=args.port, open_browser=not args.no_browser)
