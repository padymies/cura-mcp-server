"""Tier 3 (M2) group operations: group / ungroup / merge (all on the main thread)."""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def group_models(node_ids: list[str]) -> dict:
    if len(node_ids) < 2:
        raise ValueError("group_models needs at least 2 model ids.")
    return run_on_main_thread(lambda: cura_api.group_models(node_ids))


def ungroup_model(node_id: str) -> dict:
    return run_on_main_thread(lambda: cura_api.ungroup_model(node_id))


def merge_models(node_ids: list[str]) -> dict:
    if len(node_ids) < 2:
        raise ValueError("merge_models needs at least 2 model ids.")
    return run_on_main_thread(lambda: cura_api.merge_models(node_ids))
