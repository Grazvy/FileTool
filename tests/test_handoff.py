"""Files handed over by the operating system, the pages showing the app, and stopping it."""

import asyncio
import time

import pytest

from backend import desktop
from backend.app import create_app
from backend.config import Config
from launcher import app_launcher, apple_events

APP = {"X-File-Tool": "1"}
URL = "http://127.0.0.1:1234"


class FakeServer:
    def __init__(self, started=False, should_exit=False):
        self.started = started
        self.should_exit = should_exit


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    desktop.reset()
    monkeypatch.setattr(app_launcher, "_window_requested", None)
    yield
    desktop.reset()


@pytest.fixture
def opened(monkeypatch):
    """The windows the launcher opens, recorded instead of opened."""
    windows = []
    monkeypatch.setattr(app_launcher.webbrowser, "open", windows.append)
    return windows


@pytest.fixture
def opened_pdf(tmp_path, pdf_bytes):
    path = tmp_path / "opened.pdf"
    path.write_bytes(pdf_bytes)
    return path


# ---------- the queue ----------


def test_offer_queues_a_file_that_exists(opened_pdf):
    assert [entry.name for entry in desktop.offer([opened_pdf])] == ["opened.pdf"]


def test_offer_skips_a_file_that_is_not_there(tmp_path):
    assert desktop.offer([tmp_path / "gone.pdf"]) == []


def test_claim_empties_the_queue(opened_pdf):
    desktop.offer([opened_pdf])
    assert len(desktop.claim()) == 1
    assert desktop.claim() == []


def test_a_claimed_file_can_be_taken_once(opened_pdf):
    desktop.offer([opened_pdf])
    token = desktop.claim()[0].token
    assert desktop.take(token).path == opened_pdf
    assert desktop.take(token) is None


def test_only_the_last_claimed_files_stay_fetchable(opened_pdf):
    desktop.offer([opened_pdf] * (desktop.MAX_CLAIMED + 1))
    tokens = [entry.token for entry in desktop.claim()]
    assert desktop.take(tokens[0]) is None
    assert desktop.take(tokens[-1]) is not None


# ---------- open pages ----------


def test_a_page_that_connects_is_told_about_files_already_waiting(opened_pdf):
    desktop.offer([opened_pdf])
    assert desktop.connect_page().wake.is_set()


def test_a_page_with_nothing_waiting_is_left_alone():
    assert not desktop.connect_page().wake.is_set()


def test_only_the_newest_page_is_told_about_new_files(opened_pdf):
    """Two pages told at once would race, and one would end up without the file."""
    older, newer = desktop.connect_page(), desktop.connect_page()
    desktop.offer([opened_pdf])
    assert newer.wake.is_set()
    assert not older.wake.is_set()


def test_the_time_without_a_page_counts_from_the_last_one_leaving():
    first, second = desktop.connect_page(), desktop.connect_page()
    assert desktop.seconds_without_page(now=time.monotonic() + 60) == 0
    desktop.disconnect_page(first, now=100.0)
    assert desktop.seconds_without_page(now=160.0) == 0  # the second is still open
    desktop.disconnect_page(second, now=200.0)
    assert desktop.seconds_without_page(now=207.0) == 7.0


def test_a_page_disconnecting_twice_is_harmless():
    page = desktop.connect_page()
    desktop.disconnect_page(page)
    desktop.disconnect_page(page)
    assert desktop.pages_connected() == 0


# ---------- the API ----------


def test_handoff_lists_and_clears_what_was_opened(client, opened_pdf):
    desktop.offer([opened_pdf])
    files = client.get("/api/handoff", headers=APP).json()["files"]
    assert [file["name"] for file in files] == ["opened.pdf"]
    assert files[0]["size"] == opened_pdf.stat().st_size
    assert client.get("/api/handoff", headers=APP).json()["files"] == []


def test_handoff_serves_the_bytes_of_a_claimed_file(client, opened_pdf, pdf_bytes):
    desktop.offer([opened_pdf])
    token = client.get("/api/handoff", headers=APP).json()["files"][0]["token"]
    response = client.get(f"/api/handoff/{token}", headers=APP)
    assert response.status_code == 200
    assert response.content == pdf_bytes
    assert response.headers["content-type"] == "application/pdf"


def test_a_file_can_only_be_fetched_once(client, opened_pdf):
    desktop.offer([opened_pdf])
    token = client.get("/api/handoff", headers=APP).json()["files"][0]["token"]
    assert client.get(f"/api/handoff/{token}", headers=APP).status_code == 200
    assert client.get(f"/api/handoff/{token}", headers=APP).status_code == 400


def test_an_unknown_token_is_refused(client):
    assert client.get("/api/handoff/made-up", headers=APP).status_code == 400


def test_an_unsupported_file_is_refused(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a document File Tool knows")
    desktop.offer([path])
    token = client.get("/api/handoff", headers=APP).json()["files"][0]["token"]
    assert client.get(f"/api/handoff/{token}", headers=APP).status_code == 400


def test_a_file_too_large_to_load_is_refused(client, monkeypatch, opened_pdf):
    monkeypatch.setattr(Config, "MAX_UPLOAD_BYTES", 8)
    desktop.offer([opened_pdf])
    token = client.get("/api/handoff", headers=APP).json()["files"][0]["token"]
    response = client.get(f"/api/handoff/{token}", headers=APP)
    assert response.status_code == 400
    assert "larger than" in response.json()["error"]


def test_the_page_connection_says_when_files_are_waiting(client, opened_pdf):
    desktop.on_stopping(lambda: True)  # so the stream ends after one round
    desktop.offer([opened_pdf])
    assert client.get("/api/events", headers=APP).text.splitlines() == ["connected", "files"]


def test_a_quiet_page_connection_only_says_it_connected(client):
    desktop.on_stopping(lambda: True)
    assert client.get("/api/events", headers=APP).text.splitlines() == ["connected"]


def test_a_page_connection_ends_when_the_app_stops_and_is_forgotten(client):
    """An open page must never hold a stopping app up."""
    desktop.on_stopping(lambda: True)
    client.get("/api/events", headers=APP)
    assert desktop.pages_connected() == 0


def test_the_desktop_endpoints_need_the_app_header(client):
    """Without the header a browser must preflight, and no page on another
    origin can reach these."""
    assert client.get("/api/handoff").status_code == 400
    assert client.get("/api/handoff/anything").status_code == 400
    assert client.get("/api/events").status_code == 400
    assert client.post("/api/quit").status_code == 400


# ---------- quitting ----------


def test_health_reports_whether_the_app_can_be_stopped(client):
    assert client.get("/api/health").json() == {"status": "ok", "app": False}
    desktop.on_quit(lambda: None)
    assert client.get("/api/health").json()["app"] is True


def test_quit_stops_the_app(client):
    stopped = []
    desktop.on_quit(lambda: stopped.append(True))
    assert client.post("/api/quit", headers=APP).json() == {"stopping": True}
    assert stopped == [True]


def test_quit_is_refused_when_nothing_can_stop_the_server(client):
    assert client.post("/api/quit", headers=APP).status_code == 400


# ---------- windows ----------


def test_a_handed_over_file_opens_a_window_when_there_is_no_page(opened, opened_pdf):
    app_launcher.hand_over([opened_pdf], URL)
    assert opened == [URL]


def test_a_handed_over_file_goes_to_the_open_page_without_a_window(opened, opened_pdf):
    page = desktop.connect_page()
    app_launcher.hand_over([opened_pdf], URL)
    assert opened == []
    assert page.wake.is_set()


def test_a_file_handed_over_during_launch_uses_the_launch_window(opened, opened_pdf):
    """Opening a closed app with a file used to open two windows: one for the
    launch and one for the file, which reached macOS before the server was up."""
    server = FakeServer()
    thread = app_launcher.open_browser_when_ready(server, URL)
    app_launcher.hand_over([opened_pdf], URL)
    server.started = True
    thread.join(5)
    assert opened == [URL]


def test_two_reasons_at_once_open_one_window(opened):
    assert app_launcher.show_app(URL) is True
    assert app_launcher.show_app(URL) is False
    assert opened == [URL]


def test_reopening_with_no_page_open_opens_a_window(opened):
    """Clicking the icon of the running app must show it again."""
    page = desktop.connect_page()
    desktop.disconnect_page(page)
    assert app_launcher.show_app(URL) is True
    assert opened == [URL]


def test_a_window_that_never_became_a_page_stops_counting(opened):
    app_launcher.note_window_requested(
        now=time.monotonic() - app_launcher.WINDOW_GRACE_SECONDS - 1
    )
    assert app_launcher.show_app(URL) is True


def test_a_window_whose_page_was_closed_no_longer_counts(opened):
    """Closing the page and opening the app again at once must show it again,
    not wait for the first window's grace period to run out."""
    app_launcher.note_window_requested()
    page = desktop.connect_page()
    desktop.disconnect_page(page)
    assert app_launcher.show_app(URL) is True


def test_a_page_closed_right_after_its_window_opened_still_stops_the_app():
    app_launcher.note_window_requested()
    page = desktop.connect_page()
    desktop.disconnect_page(page, now=time.monotonic())
    later = time.monotonic() + app_launcher.PAGE_GRACE_SECONDS + 1
    assert app_launcher.is_unattended(now=later)


def test_a_file_that_is_gone_opens_nothing(opened, tmp_path):
    app_launcher.hand_over([tmp_path / "gone.pdf"], URL)
    assert opened == []


# ---------- stopping when the page is closed ----------


def test_the_app_is_attended_while_a_page_is_open():
    desktop.connect_page()
    assert not app_launcher.is_unattended(now=time.monotonic() + 3600)


def test_the_app_is_attended_while_its_window_is_on_its_way():
    app_launcher.note_window_requested()
    later = time.monotonic() + app_launcher.PAGE_GRACE_SECONDS + 1
    assert not app_launcher.is_unattended(now=later)


def test_a_reload_does_not_stop_the_app():
    page = desktop.connect_page()
    desktop.disconnect_page(page, now=100.0)
    assert not app_launcher.is_unattended(now=100.0 + app_launcher.PAGE_GRACE_SECONDS - 1)


def test_the_app_is_unattended_once_its_last_page_is_closed():
    page = desktop.connect_page()
    desktop.disconnect_page(page, now=100.0)
    assert app_launcher.is_unattended(now=100.0 + app_launcher.PAGE_GRACE_SECONDS + 1)


def test_the_server_stops_once_its_last_page_is_closed(tmp_path, monkeypatch):
    """Closing the tab must not leave the server running unseen."""
    monkeypatch.setattr(app_launcher, "PAGE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(app_launcher, "PAGE_GRACE_SECONDS", 0.05)
    app, server = create_app(), FakeServer()
    app_launcher.stop_when_closed(app, server, tmp_path / "FileTool.app")
    page = desktop.connect_page()

    async def scenario() -> bool:
        for hook in app.router.on_startup:
            await hook()
        await asyncio.sleep(0.1)
        kept_running = not server.should_exit
        desktop.disconnect_page(page)
        for _ in range(200):
            if server.should_exit:
                break
            await asyncio.sleep(0.01)
        return kept_running

    assert asyncio.run(scenario()) is True
    assert server.should_exit is True


def test_a_checkout_is_not_stopped_for_want_of_a_page():
    app = create_app()
    hooks = list(app.router.on_startup)
    app_launcher.stop_when_closed(app, FakeServer(), None)
    assert app.router.on_startup == hooks


# ---------- the macOS event plumbing ----------


def test_a_file_url_becomes_a_path():
    url = "file:///Users/someone/My%20Files/report%20final.pdf"
    assert str(apple_events.path_from_file_url(url)) == "/Users/someone/My Files/report final.pdf"


@pytest.mark.parametrize("url", ["http://example.com/x.pdf", "file://", ""])
def test_anything_that_is_not_a_local_file_is_ignored(url):
    assert apple_events.path_from_file_url(url) is None


def test_the_watcher_is_only_installed_on_macos(monkeypatch):
    monkeypatch.setattr(apple_events.sys, "platform", "linux")
    assert apple_events.install(lambda paths: None, lambda: None) is None


@pytest.mark.skipif(
    apple_events.sys.platform != "darwin", reason="Apple Events only exist on macOS"
)
def test_the_watcher_installs_and_polls_without_an_event():
    """With nothing sent the poll must return at once and deliver nothing."""
    delivered, reopened = [], []
    watcher = apple_events.install(delivered.append, lambda: reopened.append(True))
    assert watcher is not None
    try:
        watcher.poll()
    finally:
        watcher.stop()
    assert delivered == []
    assert reopened == []
