"""Tier 2 profile operations: list/switch machines and materials (main thread)."""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def list_machines() -> dict:
    return run_on_main_thread(cura_api.list_machines)


def switch_machine(name: str) -> dict:
    return run_on_main_thread(lambda: cura_api.switch_machine(name))


def list_materials() -> dict:
    return run_on_main_thread(cura_api.list_materials)


def switch_material(name: str) -> dict:
    return run_on_main_thread(lambda: cura_api.switch_material(name))


# --- Tier 3 (M1): nozzle variants ----------------------------------------

def list_variants() -> dict:
    return run_on_main_thread(cura_api.list_variants)


def switch_variant(name: str) -> dict:
    return run_on_main_thread(lambda: cura_api.switch_variant(name))


# --- v0.5: quality profile reads (completes set/list/get symmetry) --------

def list_quality_profiles() -> dict:
    return run_on_main_thread(cura_api.list_quality_profiles)


def get_quality() -> dict:
    return run_on_main_thread(cura_api.get_quality)
