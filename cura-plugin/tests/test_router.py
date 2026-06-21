"""Router dispatch tests that need no live Cura.

Verifies the envelope shaping and error mapping that are pure routing logic:
unknown methods, missing parameters, and that dispatch never raises.
"""
from __future__ import annotations

import importlib

router = importlib.import_module("cura_plugin.server.router")


def test_unknown_method_returns_error_envelope() -> None:
    env = router.dispatch("does_not_exist", {})
    assert env["ok"] is False
    assert env["data"] is None
    assert env["error"]["code"] == "cura_mcp_error"
    assert "Unknown method" in env["error"]["message"]


def test_missing_parameter_is_reported() -> None:
    # load_model requires params["path"]; omitting it must yield a clean error,
    # not a raised KeyError.
    env = router.dispatch("load_model", {})
    assert env["ok"] is False
    assert env["error"]["code"] == "cura_mcp_error"
    assert "Missing parameter" in env["error"]["message"]


def test_clear_plate_is_registered() -> None:
    # clear_plate is a known method (not "Unknown method"); without a live Cura
    # it fails on the main-thread dispatcher, but as a structured envelope.
    env = router.dispatch("clear_plate", {})
    assert env["ok"] is False
    assert "Unknown method" not in env["error"]["message"]


def test_dispatch_never_raises_on_internal_failure() -> None:
    # get_status reaches the main-thread dispatcher, which is uninitialised in
    # this harness; the failure must surface as an envelope, never an exception.
    env = router.dispatch("get_status", {})
    assert env["ok"] is False
    assert env["error"]["code"] == "cura_mcp_error"
