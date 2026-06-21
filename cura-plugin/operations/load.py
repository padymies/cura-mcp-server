"""load_model operation: sandbox the path, then load the mesh asynchronously.

The path sandbox is a SECURITY control (see docs/security-model.md): only allowed
directories, no traversal, only permitted extensions.

Loading is ASYNCHRONOUS in Cura: ``readLocalFile`` spawns a background
ReadMeshJob and the node only appears in the scene later (on the main thread,
when ``CuraApplication.fileCompleted`` fires). So this mirrors the slice
handshake: subscribe on the main thread, trigger, then block the HTTP worker
thread on a ``threading.Event`` until the load settles, and only then resolve the
node id. Blocking inside a main-thread call would deadlock the very signal we
wait for, so the wait MUST happen on the worker thread.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread
from ..errors import InvalidPath, LoadFailed

ALLOWED_EXTENSIONS = {".stl", ".3mf", ".obj"}
_LOAD_TIMEOUT = 120.0


_ALLOWED_DIRS_ENV = "CURA_MCP_ALLOWED_DIRS"


def _allowed_roots() -> list[Path]:
    """Directories ``load_model`` may read from — the sandbox boundary.

    Override with the ``CURA_MCP_ALLOWED_DIRS`` env var (``os.pathsep``-separated
    absolute paths). When unset, default to the user's home directory plus a
    dedicated ``~/3D Models`` folder if it exists. Keep this tight: any path
    outside these roots is rejected by ``_validate_path``.
    """
    raw = os.environ.get(_ALLOWED_DIRS_ENV)
    if raw:
        roots = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
    else:
        home = Path.home()
        roots = [home, home / "3D Models"]

    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve(strict=True))
        except OSError:
            continue  # skip configured dirs that don't exist
    if not resolved:
        # Never fall through to an empty allow-list (which would reject nothing
        # cleanly but signal a misconfiguration); home always exists.
        resolved.append(Path.home().resolve())
    return resolved


def _validate_path(raw: str) -> Path:
    if not raw:
        raise InvalidPath("Empty path.")
    path = Path(raw)
    if ".." in path.parts:
        raise InvalidPath("Path traversal is not allowed.")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InvalidPath(f"File not found: {raw}") from exc
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidPath(
            f"Unsupported extension '{resolved.suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}."
        )
    roots = [r.resolve() for r in _allowed_roots()]
    if not any(_is_within(resolved, root) for root in roots):
        raise InvalidPath("Path is outside the allowed directories.")
    return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_model(path: str) -> dict:
    safe = _validate_path(path)
    return _load_and_wait(os.fspath(safe))


def _load_and_wait(path: str, timeout: float = _LOAD_TIMEOUT) -> dict:
    settled = threading.Event()

    def on_complete(_filename: str) -> None:
        # Runs on the main thread (signal context). Latch the first completion
        # after we triggered; for the single-model v1 flow that is our load.
        settled.set()

    def _setup() -> object:
        token = cura_api.subscribe_file_completed(on_complete)
        cura_api.trigger_load(path)  # async; returns immediately
        return token

    token = run_on_main_thread(_setup)
    try:
        if not settled.wait(timeout):
            raise LoadFailed(f"Model load did not complete within {timeout:.0f}s.")
    finally:
        run_on_main_thread(lambda: cura_api.unsubscribe_file_completed(token))

    # A plain readLocalFile does NOT auto-arrange a .3mf onto the plate, so the
    # node can land off-plate on corner-origin machines. Arrange it onto the
    # build plate, THEN resolve, so load_model returns the post-arrange truth.
    def _arrange_and_resolve() -> dict:
        cura_api.arrange_loaded_node()
        return cura_api.resolve_loaded_node()

    return run_on_main_thread(_arrange_and_resolve)
