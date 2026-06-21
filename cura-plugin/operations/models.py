"""Tier 1 model-management operations: list / select / remove / duplicate /
arrange_all. All marshal to Cura's main thread (they read or mutate the scene).
"""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def list_models() -> dict:
    return {"models": run_on_main_thread(cura_api.list_nodes)}


def select_model(node_id: str) -> dict:
    return run_on_main_thread(lambda: cura_api.select_node(node_id))


def remove_model(node_id: str) -> dict:
    return run_on_main_thread(lambda: cura_api.remove_node(node_id))


def duplicate_model(node_id: str, count: int = 1) -> dict:
    return run_on_main_thread(lambda: cura_api.duplicate_node(node_id, int(count)))


def arrange_all() -> dict:
    return run_on_main_thread(cura_api.arrange_all)
