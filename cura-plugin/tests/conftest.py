"""Test harness for the Cura plugin's Cura-free logic.

The plugin runs inside Cura's interpreter (PyQt + cura/UM available). To unit-test
the parts that do NOT need a live Cura — auth, the load_model path sandbox, and
router dispatch — we register the plugin directory as an importable package
(``cura_plugin``) and inject minimal stubs for PyQt/cura/UM so the modules import
without a Qt event loop. No Cura behaviour is exercised here; the adapter and the
slice handshake are validated manually (see docs/manual-smoke-test.md).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]  # cura-plugin/


def _install_pyqt_stub() -> None:
    if "PyQt6.QtCore" in sys.modules:
        return

    class _SignalInstance:
        def connect(self, *a: object, **k: object) -> None: ...
        def disconnect(self, *a: object, **k: object) -> None: ...
        def emit(self, *a: object, **k: object) -> None: ...

    class pyqtSignal:  # noqa: N801 - mirror PyQt name
        def __init__(self, *a: object, **k: object) -> None: ...

        def __get__(self, obj: object, objtype: object = None) -> _SignalInstance:
            return _SignalInstance()

    def pyqtSlot(*a: object, **k: object):  # noqa: ANN202, N802
        def deco(fn):  # noqa: ANN001, ANN202
            return fn

        return deco

    class QObject:
        def __init__(self, *a: object, **k: object) -> None: ...

        def thread(self) -> object:
            return None

    class QThread:
        @staticmethod
        def currentThread() -> object:  # noqa: N802
            return object()

    class _ConnType:
        QueuedConnection = 0

    class Qt:
        ConnectionType = _ConnType

    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.QObject = QObject
    qtcore.QThread = QThread
    qtcore.Qt = Qt
    qtcore.pyqtSignal = pyqtSignal
    qtcore.pyqtSlot = pyqtSlot
    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qtcore
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore


def _register_plugin_package() -> None:
    if "cura_plugin" in sys.modules:
        return
    pkg = types.ModuleType("cura_plugin")
    pkg.__path__ = [str(PLUGIN_DIR)]  # type: ignore[attr-defined]
    sys.modules["cura_plugin"] = pkg


_install_pyqt_stub()
_register_plugin_package()
