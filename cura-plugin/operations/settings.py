"""Tier 2 settings operations: get / set / reset (all on the main thread)."""
from __future__ import annotations

from typing import Any

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def get_setting(key: str) -> dict:
    return run_on_main_thread(lambda: cura_api.get_setting(key))


def set_setting(key: str, value: Any) -> dict:
    return run_on_main_thread(lambda: cura_api.set_setting(key, value))


def reset_setting(key: str) -> dict:
    return run_on_main_thread(lambda: cura_api.reset_setting(key))


# --- curated writers (validate the argument, then delegate to set_setting) -

def set_layer_height(mm: float) -> dict:
    mm = float(mm)
    if mm <= 0:
        raise ValueError("layer_height must be a positive number of mm.")
    return run_on_main_thread(lambda: cura_api.set_setting("layer_height", mm))


def set_infill_density(percent: float) -> dict:
    percent = float(percent)
    if not 0.0 <= percent <= 100.0:
        raise ValueError("infill density must be between 0 and 100 (percent).")
    return run_on_main_thread(lambda: cura_api.set_setting("infill_sparse_density", percent))


def set_supports(enabled: bool, type: str | None = None) -> dict:  # noqa: A002
    placement: str | None = None
    if type is not None:
        placement = str(type).lower()
        if placement not in ("everywhere", "buildplate"):
            raise ValueError("support type must be 'everywhere' or 'buildplate'.")
    return run_on_main_thread(lambda: cura_api.set_supports(bool(enabled), placement))


def set_adhesion(type: str) -> dict:  # noqa: A002
    value = str(type).lower()
    if value not in ("skirt", "brim", "raft", "none"):
        raise ValueError("adhesion type must be one of: skirt, brim, raft, none.")
    return run_on_main_thread(lambda: cura_api.set_setting("adhesion_type", value))


def set_quality(preset: str) -> dict:
    return run_on_main_thread(lambda: cura_api.set_quality_preset(str(preset).lower()))
