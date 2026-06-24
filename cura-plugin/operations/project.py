"""Tier 3 (M3) project operations: save / open a full Cura workspace (.3mf).

``save_project`` reuses the export output-sandbox (restricted to .3mf — a project
must be a 3MF so the name matches the bytes).

``open_project`` is DESTRUCTIVE and two-step by design:

* ``confirm=False`` (default) returns a non-mutating PREVIEW — it validates the
  file is a readable project (via the adapter's non-destructive preRead) and
  reports the current workspace + what proceeding would do; nothing changes.
* ``confirm=True`` actually opens it, in one of two ``mode`` s:
    - ``create_new`` — loads into a fresh printer instance (verified path);
    - ``replace_active`` — overwrites the active printer in place (gated in the
      adapter until its override path is verified against installed Cura source).

The open runs as a single synchronous main-thread call (no async signal handshake,
unlike load_model) and returns a before/after summary.
"""
from __future__ import annotations

import os

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread
from ..errors import LoadFailed
from .export import _validate_output_path
from .load import _validate_path

_PROJECT_EXTENSIONS = {".3mf"}
_VALID_MODES = {"create_new", "replace_active"}


def save_project(path: str) -> dict:
    safe = _validate_output_path(path, _PROJECT_EXTENSIONS)
    return run_on_main_thread(lambda: cura_api.save_project(os.fspath(safe)))


def open_project(path: str, confirm: bool = False, mode: str = "create_new") -> dict:
    safe = _validate_path(path)
    target = os.fspath(safe)
    if mode not in _VALID_MODES:
        raise LoadFailed(f"Unknown mode '{mode}'. Use create_new or replace_active.")

    # Opening always discards the current plate; replace_active also overwrites the
    # active printer's profile. Either way it is destructive with no undo.
    destructive = True

    def _preview() -> dict:
        before = cura_api.workspace_summary()
        info = cura_api.preview_project_workspace(target)  # non-destructive validation
        if mode == "replace_active":
            note = (
                f"PREVIEW — nothing changed. Proceeding would OVERWRITE the active "
                f"printer '{before['machine']}' (profile, material, settings) with the "
                f"project's, in place, and replace the current plate "
                f"({before['models']} models). NO undo — run save_project first if "
                f"unsure, and note it only works if the project was made for the same "
                f"printer. (replace_active may be gated off pending source verification; "
                f"if so, confirm=true returns load_failed — use create_new.) Re-call with "
                f"confirm=true once the user agrees."
            )
        else:
            note = (
                f"PREVIEW — nothing changed. Proceeding would create a NEW printer from "
                f"the project '{info.get('name') or target}' and load its scene, replacing "
                f"the current plate ({before['models']} models on '{before['machine']}'). "
                f"The current printer stays in the list. NO undo. Re-call with confirm=true "
                f"once the user agrees."
            )
        return {
            "applied": False,
            "mode": mode,
            "destructive": destructive,
            "previous_machine": before["machine"],
            "previous_models": before["models"],
            "machine": None,
            "models": None,
            "note": note,
        }

    def _execute() -> dict:
        before = cura_api.workspace_summary()
        opened = cura_api.open_project_workspace(target, mode)
        after = cura_api.workspace_summary()
        return {
            "applied": True,
            "mode": mode,
            "destructive": destructive,
            "previous_machine": before["machine"],
            "previous_models": before["models"],
            "machine": after["machine"],
            # open_project_workspace counts the nodes it just added (reliable even
            # before the scene settles); fall back to the post-settle count.
            "models": opened.get("models", after["models"]),
            "note": opened.get("note"),
        }

    return run_on_main_thread(_execute if confirm else _preview)
