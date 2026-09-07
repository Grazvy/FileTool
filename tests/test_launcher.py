import contextlib
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from launcher import app_launcher

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with contextlib.closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_reserve_socket_uses_the_requested_port():
    port = free_port()
    sock = app_launcher.reserve_socket("127.0.0.1", port)
    with contextlib.closing(sock):
        assert sock.getsockname()[1] == port


def test_reserve_socket_falls_back_when_the_port_is_taken():
    taken = app_launcher.reserve_socket("127.0.0.1", free_port())
    with contextlib.closing(taken):
        fallback = app_launcher.reserve_socket("127.0.0.1", taken.getsockname()[1])
        with contextlib.closing(fallback):
            assert fallback.getsockname()[1] != taken.getsockname()[1]


class FakeServer:
    def __init__(self, started=False, should_exit=False):
        self.started = started
        self.should_exit = should_exit


def test_browser_opens_once_the_server_is_started(monkeypatch):
    opened = []
    monkeypatch.setattr(app_launcher.webbrowser, "open", opened.append)
    app_launcher.open_browser_when_ready(FakeServer(started=True), "http://127.0.0.1:1234").join(5)
    assert opened == ["http://127.0.0.1:1234"]


def test_browser_does_not_open_when_the_server_is_stopping(monkeypatch):
    opened = []
    monkeypatch.setattr(app_launcher.webbrowser, "open", opened.append)
    server = FakeServer(should_exit=True)
    app_launcher.open_browser_when_ready(server, "http://127.0.0.1:1234").join(5)
    assert opened == []


def test_shutdown_handler_stops_the_server():
    server = FakeServer()
    original = signal.getsignal(signal.SIGTERM)
    try:
        app_launcher.install_shutdown_handlers(server)
        signal.raise_signal(signal.SIGTERM)
    finally:
        signal.signal(signal.SIGTERM, original)
    assert server.should_exit is True


def test_run_reports_a_missing_frontend(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app_launcher.Config, "FRONTEND_DIR", tmp_path / "absent")
    assert app_launcher.run(open_browser=False) == 1
    assert "not found" in capsys.readouterr().err


def test_main_passes_arguments_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(app_launcher, "run", lambda **kwargs: captured.update(kwargs) or 0)
    assert app_launcher.main(["--host", "0.0.0.0", "--port", "9123", "--no-browser"]) == 0
    assert captured == {"host": "0.0.0.0", "port": 9123, "open_browser": False}


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_launcher_serves_the_app_and_shuts_down_on_signal(stop_signal):
    """The launched process must serve the app and exit cleanly when terminated."""
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "main.py", "--port", str(port), "--no-browser"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert _wait_for_health(f"http://127.0.0.1:{port}/api/health", process)
        process.send_signal(stop_signal)
        assert process.wait(timeout=15) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    # The port is released, so a second launch gets it back instead of falling
    # back to another one.
    with contextlib.closing(app_launcher.reserve_socket("127.0.0.1", port)) as relaunch:
        assert relaunch.getsockname()[1] == port


def _wait_for_health(url: str, process: subprocess.Popen, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"launcher exited early:\n{process.stdout.read()}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status == 200
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    return False
