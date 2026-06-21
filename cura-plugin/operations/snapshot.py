"""get_snapshot operation: render the plate to a PNG (main thread: GL render)."""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def get_snapshot(width: int = 600, height: int = 600) -> dict:
    return run_on_main_thread(lambda: cura_api.snapshot_png(int(width), int(height)))
