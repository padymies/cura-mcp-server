"""clear_plate operation: remove all loaded models from the active build plate.

Pure orchestration; the Cura-touching work is in adapters.cura_api. Runs on the
main thread (mutates the scene) via run_on_main_thread.
"""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def clear_plate() -> dict:
    cleared = run_on_main_thread(cura_api.clear_build_plate)
    return {"cleared": int(cleared)}
