"""export_model operation: sandbox the OUTPUT path, then write the mesh to disk.

The output sandbox mirrors load_model's input sandbox (allow-list, no traversal,
allowed extension) — a write is at least as sensitive as a read. The file need
not exist yet, so we validate the normalised path and its parent directory rather
than requiring the file to be present.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread
from ..errors import InvalidPath
from .load import _allowed_roots, _is_within

ALLOWED_EXPORT_EXTENSIONS = {".stl", ".3mf"}


def _validate_output_path(raw: str) -> Path:
    if not raw:
        raise InvalidPath("Empty path.")
    path = Path(raw)
    if ".." in path.parts:
        raise InvalidPath("Path traversal is not allowed.")
    # Output file may not exist yet — normalise without requiring it.
    resolved = Path(os.path.abspath(path.expanduser()))
    if resolved.suffix.lower() not in ALLOWED_EXPORT_EXTENSIONS:
        raise InvalidPath(
            f"Unsupported extension '{resolved.suffix}'. Allowed: {sorted(ALLOWED_EXPORT_EXTENSIONS)}."
        )
    if not resolved.parent.exists():
        raise InvalidPath(f"Target directory does not exist: {resolved.parent}")
    roots = [r.resolve() for r in _allowed_roots()]
    if not any(_is_within(resolved, root) for root in roots):
        raise InvalidPath("Path is outside the allowed directories.")
    return resolved


def export_model(target: str = "all", path: str = "", fmt: str = "stl") -> dict:
    safe = _validate_output_path(path)
    # The file extension is the source of truth for the format (so the bytes match
    # the name); the explicit fmt is only a hint.
    resolved_fmt = safe.suffix.lstrip(".").lower()
    node_id = None if target in (None, "", "all") else target
    return run_on_main_thread(lambda: cura_api.export_mesh(os.fspath(safe), resolved_fmt, node_id))
