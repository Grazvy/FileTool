"""Files the operating system hands the app, the pages showing it, and stopping it.

This module is the one place where the server keeps something between requests,
and it is deliberate: a desktop app is handed files by the OS, not over HTTP, and
it has to know whether anyone is still looking at it.

"Open with" gives the app a path, which waits here until a page asks for it. Each
open page holds one connection to the app for as long as it is open: that is how
files reach it the moment they arrive, and how the launcher knows when the last
page is gone. Nothing in here is ever filled from an upload, so the server still
stores nothing a client sent it.
"""

import asyncio
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# A claimed file stays fetchable only until the page comes for its bytes; this
# cap keeps a page that claims and never fetches from growing the map forever.
MAX_CLAIMED = 16


@dataclass(frozen=True)
class Pending:
    """A file the OS asked the app to open."""

    token: str
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size(self) -> int:
        return self.path.stat().st_size


@dataclass(eq=False)
class Page:
    """An open page, for as long as its connection to the app lasts."""

    # Set when files are waiting for this page to claim them.
    wake: asyncio.Event = field(default_factory=asyncio.Event)


_pending: list[Pending] = []
_claimed: OrderedDict[str, Pending] = OrderedDict()
_pages: list[Page] = []  # oldest first
_last_page_joined: float | None = None
_last_page_left: float = time.monotonic()
_quit: Callable[[], None] | None = None
_stopping: Callable[[], bool] | None = None


def offer(paths: Iterable[str | Path]) -> list[Pending]:
    """Queue files for a page to pick up, skipping any that are not there.

    Called by the launcher with paths from the OS, never from a request.
    """
    added = []
    for path in paths:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            continue
        entry = Pending(token=secrets.token_urlsafe(16), path=resolved)
        _pending.append(entry)
        added.append(entry)
    if added and _pages:
        # Only the page opened last is told. Two pages told at once would both
        # claim, and one would end up with the file and the other without.
        _pages[-1].wake.set()
    return added


def claim() -> list[Pending]:
    """Hand the queued files to the page and empty the queue.

    The entries stay fetchable by token so the page can come back for the bytes.
    """
    taken = list(_pending)
    _pending.clear()
    for entry in taken:
        _claimed[entry.token] = entry
        while len(_claimed) > MAX_CLAIMED:
            _claimed.popitem(last=False)
    return taken


def take(token: str) -> Pending | None:
    """Look up a claimed file by its token, forgetting it in the process."""
    return _claimed.pop(token, None)


def connect_page(now: float | None = None) -> Page:
    """Register a page that just opened its connection to the app."""
    global _last_page_joined
    page = Page()
    _pages.append(page)
    _last_page_joined = time.monotonic() if now is None else now
    if _pending:
        page.wake.set()  # files handed over before any page was there to take them
    return page


def disconnect_page(page: Page, now: float | None = None) -> None:
    """Forget a page whose connection closed: its tab was closed or reloaded."""
    global _last_page_left
    if page not in _pages:
        return
    _pages.remove(page)
    if not _pages:
        _last_page_left = time.monotonic() if now is None else now


def pages_connected() -> int:
    return len(_pages)


def last_page_joined() -> float | None:
    """When a page last connected, or None if none has since the launch."""
    return _last_page_joined


def seconds_without_page(now: float | None = None) -> float:
    """How long the app has had no open page; zero while it has one.

    Before any page ever connected, this counts from the last reset — the launch.
    """
    if _pages:
        return 0.0
    current = time.monotonic() if now is None else now
    return current - _last_page_left


def on_quit(callback: Callable[[], None] | None) -> None:
    """Register how to stop the app. Only the launcher knows how."""
    global _quit
    _quit = callback


def can_quit() -> bool:
    """Whether the app can stop itself, i.e. whether it runs under the launcher."""
    return _quit is not None


def request_quit() -> bool:
    """Ask the app to shut down. False when nothing knows how to."""
    if _quit is None:
        return False
    _quit()
    return True


def on_stopping(check: Callable[[], bool] | None) -> None:
    """Register how to tell that the app is shutting down.

    The server waits for every connection to close before it stops, so a page's
    connection has to end by itself once this says so.
    """
    global _stopping
    _stopping = check


def is_stopping() -> bool:
    return _stopping is not None and _stopping()


def reset() -> None:
    """Forget everything. For tests and for a fresh launch."""
    global _last_page_joined, _last_page_left, _quit, _stopping
    _pending.clear()
    _claimed.clear()
    _pages.clear()
    _last_page_joined = None
    _last_page_left = time.monotonic()
    _quit = None
    _stopping = None
