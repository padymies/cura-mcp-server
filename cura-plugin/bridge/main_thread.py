"""Marshal callables onto Cura's Qt main (UI) thread.

Scene, mesh, and backend operations in Cura MUST run on the main thread. The
plugin's HTTP server runs on a worker thread, so every mutating operation is
dispatched here. This is the single place that crosses the thread boundary.

Mechanism: a QObject created on the main thread exposes a queued-connection
signal. Emitting it from a worker thread runs the slot on the main thread; a
``threading.Event`` lets the worker block for the result (or exception).

NOTE (version-sensitive): Cura 5.x uses PyQt6. The import falls back to PyQt5 for
older bases. Confirm the binding against the target Cura version (Phase 3).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

try:  # Cura 5.x
    from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot

    _QUEUED = Qt.ConnectionType.QueuedConnection
except ImportError:  # pragma: no cover - older Cura bases
    from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot

    _QUEUED = Qt.QueuedConnection  # type: ignore[attr-defined]


class _Call:
    """A unit of work plus a latch for its result, executed on the main thread."""

    __slots__ = ("_fn", "_event", "_result", "_error")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn
        self._event = threading.Event()
        self._result: Any = None
        self._error: BaseException | None = None

    def execute(self) -> None:
        try:
            self._result = self._fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            self._error = exc
        finally:
            self._event.set()

    def wait(self, timeout: float | None) -> Any:
        if not self._event.wait(timeout):
            raise TimeoutError("Main-thread call timed out")
        if self._error is not None:
            raise self._error
        return self._result


class _MainThreadDispatcher(QObject):
    _invoke = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        # Queued connection guarantees the slot runs on this object's (main) thread.
        self._invoke.connect(self._run, _QUEUED)

    @pyqtSlot(object)
    def _run(self, call: _Call) -> None:
        call.execute()

    def dispatch(self, call: _Call) -> None:
        self._invoke.emit(call)


_dispatcher: _MainThreadDispatcher | None = None


def init_main_thread_dispatcher() -> None:
    """Create the dispatcher. MUST be called from the main thread (plugin start)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _MainThreadDispatcher()


def run_on_main_thread(fn: Callable[[], Any], timeout: float | None = 30.0) -> Any:
    """Run ``fn`` on Cura's main thread; return its result or raise its exception.

    Safe to call from the HTTP worker thread. If already on the main thread, runs
    inline to avoid deadlocking on the event we'd never get to process.
    """
    if _dispatcher is None:
        raise RuntimeError(
            "Main-thread dispatcher not initialized. Call "
            "init_main_thread_dispatcher() from the main thread during plugin start."
        )
    if QThread.currentThread() is _dispatcher.thread():
        return fn()
    call = _Call(fn)
    _dispatcher.dispatch(call)
    return call.wait(timeout)
