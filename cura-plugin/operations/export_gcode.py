"""export_gcode operation: sandbox the .gcode output path, gate on a DONE slice.

Reuses the export output-path sandbox (allow-list, no traversal) with a .gcode
extension. The adapter additionally refuses to write unless a completed slice's
G-code is actually available, so we never produce an empty/stale file.
"""
from __future__ import annotations

import os

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread
from .export import _validate_output_path

ALLOWED_GCODE_EXTENSIONS = {".gcode", ".gco", ".g"}


def export_gcode(path: str) -> dict:
    safe = _validate_output_path(path, ALLOWED_GCODE_EXTENSIONS)
    return run_on_main_thread(lambda: cura_api.export_gcode(os.fspath(safe)))
