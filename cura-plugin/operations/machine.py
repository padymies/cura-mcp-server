"""get_machine_info operation (main thread: reads the active machine stack)."""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def get_machine_info() -> dict:
    return run_on_main_thread(cura_api.get_machine_info)
