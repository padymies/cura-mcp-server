"""Tier 1 router dispatch tests (no live Cura).

Confirms the new model-management methods are registered (reach the main-thread
dispatcher, not "Unknown method") and that missing params surface as structured
errors rather than raised exceptions.
"""
from __future__ import annotations

import importlib

router = importlib.import_module("cura_plugin.server.router")

_TIER1_METHODS = (
    "list_models",
    "select_model",
    "remove_model",
    "duplicate_model",
    "arrange_all",
    "scale_model",
    "mirror_model",
    "move_model",
    "center_model",
    "scale_to_fit",
    "get_machine_info",
    "get_snapshot",
)


def test_tier1_methods_are_registered() -> None:
    for method in _TIER1_METHODS:
        env = router.dispatch(method, {"node_id": "x", "axis": "x"})
        assert env["ok"] is False  # no live Cura in the harness
        assert "Unknown method" not in env["error"]["message"]


def test_export_model_is_registered_and_requires_path() -> None:
    # Registered (not "Unknown method") but missing the required path param.
    env = router.dispatch("export_model", {})
    assert env["ok"] is False
    assert "Unknown method" not in env["error"]["message"]
    assert "Missing parameter" in env["error"]["message"]


def test_select_model_missing_node_id_is_structured() -> None:
    env = router.dispatch("select_model", {})
    assert env["ok"] is False
    assert "Missing parameter" in env["error"]["message"]


def test_remove_model_missing_node_id_is_structured() -> None:
    env = router.dispatch("remove_model", {})
    assert env["ok"] is False
    assert "Missing parameter" in env["error"]["message"]
