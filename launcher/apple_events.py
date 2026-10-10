"""Receive what macOS sends the app through "Open with" and through opening it again.

macOS does not pass opened files on the command line. It sends the application
an `odoc` Apple Event — at launch, and again every time a file is opened while
the app is already running, because LaunchServices activates the running copy
instead of starting a second one. An app that never reads those events gets the
first file only if its bootloader translated it into argv, and silently drops
every later one.

Opening the app itself while it runs — its icon in the Applications folder,
Launchpad or Spotlight — likewise starts nothing: macOS sends the running copy a
`rapp` (reopen) event, and an app that ignores it simply does not respond.

So the handlers stay installed for the life of the process and the queue is
polled, with a zero timeout, from the server's own event loop: the poll returns
at once when there is nothing there, and the Carbon event queue belongs to the
main thread, which is the thread uvicorn runs on.

Everything here is ctypes against frameworks macOS already ships. On any other
platform, or if the frameworks cannot be loaded, `install` returns None and the
app runs exactly as before.
"""

import asyncio
import ctypes
import sys
import urllib.parse
from pathlib import Path
from typing import Callable

CARBON = "/System/Library/Frameworks/Carbon.framework/Carbon"

POLL_SECONDS = 0.25
_URL_BUFFER_BYTES = 4096


def _four_char_code(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


_CORE_EVENT_CLASS = _four_char_code("aevt")
_OPEN_DOCUMENTS = _four_char_code("odoc")
_REOPEN_APPLICATION = _four_char_code("rapp")
_DIRECT_OBJECT = _four_char_code("----")
_TYPE_LIST = _four_char_code("list")
_TYPE_FILE_URL = _four_char_code("furl")
_EVENT_CLASS_APPLE_EVENT = _four_char_code("eppc")
_EVENT_APPLE_EVENT = 1


class _AEDesc(ctypes.Structure):
    _fields_ = [("descriptorType", ctypes.c_uint32), ("dataHandle", ctypes.c_void_p)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventRecord(ctypes.Structure):
    _fields_ = [
        ("what", ctypes.c_uint16),
        ("message", ctypes.c_uint32),
        ("when", ctypes.c_uint32),
        ("where_v", ctypes.c_int16),
        ("where_h", ctypes.c_int16),
        ("modifiers", ctypes.c_uint16),
    ]


_HANDLER = ctypes.CFUNCTYPE(
    ctypes.c_int16, ctypes.POINTER(_AEDesc), ctypes.POINTER(_AEDesc), ctypes.c_void_p
)


class Watcher:
    """The installed Apple Event handlers and the poll that delivers what they caught."""

    def __init__(
        self,
        carbon: ctypes.CDLL,
        on_files: Callable[[list[Path]], None],
        on_reopen: Callable[[], None] | None = None,
    ):
        self._carbon = carbon
        self._on_files = on_files
        self._on_reopen = on_reopen
        self._spec = _EventTypeSpec(_EVENT_CLASS_APPLE_EVENT, _EVENT_APPLE_EVENT)
        # Kept on the instance: ctypes callbacks are only alive while referenced,
        # and these are called by the OS long after install() returns.
        self._files_callback = _HANDLER(self._handle_files)
        self._reopen_callback = _HANDLER(self._handle_reopen)
        self.stopped = False

    def install(self) -> bool:
        installed = self._carbon.AEInstallEventHandler(
            _CORE_EVENT_CLASS, _OPEN_DOCUMENTS, self._files_callback, None, False
        ) == 0
        if installed and self._on_reopen is not None:
            self._carbon.AEInstallEventHandler(
                _CORE_EVENT_CLASS, _REOPEN_APPLICATION, self._reopen_callback, None, False
            )
        return installed

    def poll(self) -> None:
        """Deliver every Apple Event waiting right now, then return.

        Never blocks: the timeout is zero, so an empty queue costs one call.
        """
        while not self.stopped and self._process_one():
            pass

    async def run(self) -> None:
        """Poll until stopped. Runs as a task on the server's event loop."""
        while not self.stopped:
            try:
                self.poll()
            except Exception as error:  # a broken event must not stop the server
                print(f"Could not read an Apple Event: {error}", file=sys.stderr)
            await asyncio.sleep(POLL_SECONDS)

    def stop(self) -> None:
        self.stopped = True

    def _process_one(self) -> bool:
        event = ctypes.c_void_p()
        status = self._carbon.ReceiveNextEvent(
            1, ctypes.byref(self._spec), 0.0, True, ctypes.byref(event)
        )
        if status != 0 or not event:
            return False
        try:
            record = _EventRecord()
            if self._carbon.ConvertEventRefToEventRecord(event, ctypes.byref(record)):
                # Calls one of the handlers below, on this thread, before returning.
                self._carbon.AEProcessAppleEvent(ctypes.byref(record))
        finally:
            self._carbon.ReleaseEvent(event)
        return True

    def _handle_files(self, event, _reply, _refcon) -> int:
        """Carbon calls this with an `odoc` event. Must never raise into C."""
        try:
            paths = self._paths_in(event)
            if paths:
                self._on_files(paths)
        except Exception as error:
            print(f"Could not open the file macOS handed over: {error}", file=sys.stderr)
        return 0

    def _handle_reopen(self, _event, _reply, _refcon) -> int:
        """Carbon calls this with a `rapp` event. Must never raise into C."""
        try:
            if self._on_reopen is not None:
                self._on_reopen()
        except Exception as error:
            print(f"Could not reopen the app: {error}", file=sys.stderr)
        return 0

    def _paths_in(self, event) -> list[Path]:
        documents = _AEDesc()
        if self._carbon.AEGetParamDesc(
            event, _DIRECT_OBJECT, _TYPE_LIST, ctypes.byref(documents)
        ) != 0:
            return []
        try:
            count = ctypes.c_long(0)
            self._carbon.AECountItems(ctypes.byref(documents), ctypes.byref(count))
            return [
                path
                for index in range(1, count.value + 1)
                if (path := self._path_at(documents, index)) is not None
            ]
        finally:
            self._carbon.AEDisposeDesc(ctypes.byref(documents))

    def _path_at(self, documents: _AEDesc, index: int) -> Path | None:
        buffer = ctypes.create_string_buffer(_URL_BUFFER_BYTES)
        keyword, kind, actual = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_long()
        status = self._carbon.AEGetNthPtr(
            ctypes.byref(documents),
            index,
            _TYPE_FILE_URL,
            ctypes.byref(keyword),
            ctypes.byref(kind),
            buffer,
            _URL_BUFFER_BYTES,
            ctypes.byref(actual),
        )
        if status != 0:
            return None
        return path_from_file_url(buffer.raw[: actual.value].decode("utf-8", "replace"))


def path_from_file_url(url: str) -> Path | None:
    """Turn the `file://` URL an Apple Event carries into a path."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "file" or not parsed.path:
        return None
    return Path(urllib.parse.unquote(parsed.path))


def install(
    on_files: Callable[[list[Path]], None], on_reopen: Callable[[], None] | None = None
) -> Watcher | None:
    """Start listening for opened files and reopening. None when macOS cannot provide them."""
    if sys.platform != "darwin":
        return None
    try:
        carbon = ctypes.CDLL(CARBON)
        _declare(carbon)
    except OSError:
        return None

    watcher = Watcher(carbon, on_files, on_reopen)
    return watcher if watcher.install() else None


def _declare(carbon: ctypes.CDLL) -> None:
    """Give every call its argument types, so ctypes cannot guess them wrong."""
    carbon.AEInstallEventHandler.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32, _HANDLER, ctypes.c_void_p, ctypes.c_bool
    ]
    carbon.AEInstallEventHandler.restype = ctypes.c_int32
    carbon.AEGetParamDesc.argtypes = [
        ctypes.POINTER(_AEDesc), ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(_AEDesc)
    ]
    carbon.AEGetParamDesc.restype = ctypes.c_int32
    carbon.AECountItems.argtypes = [ctypes.POINTER(_AEDesc), ctypes.POINTER(ctypes.c_long)]
    carbon.AECountItems.restype = ctypes.c_int32
    carbon.AEGetNthPtr.argtypes = [
        ctypes.POINTER(_AEDesc), ctypes.c_long, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p, ctypes.c_long, ctypes.POINTER(ctypes.c_long),
    ]
    carbon.AEGetNthPtr.restype = ctypes.c_int32
    carbon.AEDisposeDesc.argtypes = [ctypes.POINTER(_AEDesc)]
    carbon.AEDisposeDesc.restype = ctypes.c_int32
    carbon.ReceiveNextEvent.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(_EventTypeSpec), ctypes.c_double,
        ctypes.c_bool, ctypes.POINTER(ctypes.c_void_p),
    ]
    carbon.ReceiveNextEvent.restype = ctypes.c_int32
    carbon.ConvertEventRefToEventRecord.argtypes = [ctypes.c_void_p, ctypes.POINTER(_EventRecord)]
    carbon.ConvertEventRefToEventRecord.restype = ctypes.c_bool
    carbon.AEProcessAppleEvent.argtypes = [ctypes.POINTER(_EventRecord)]
    carbon.AEProcessAppleEvent.restype = ctypes.c_int32
    carbon.ReleaseEvent.argtypes = [ctypes.c_void_p]
    carbon.ReleaseEvent.restype = None
