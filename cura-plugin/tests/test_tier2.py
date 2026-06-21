"""Tier 2 router registration, curated-writer validation, and gcode sandbox.

No live Cura: curated writers validate their argument BEFORE touching Cura (so the
reject paths are testable headlessly), and the gcode output path reuses the export
sandbox with a .gcode extension.
"""
from __future__ import annotations

import importlib
import os

import pytest

router = importlib.import_module("cura_plugin.server.router")
settings_op = importlib.import_module("cura_plugin.operations.settings")
from cura_plugin.errors import InvalidPath  # noqa: E402 - after package registration
from cura_plugin.operations.export import _validate_output_path  # noqa: E402
from cura_plugin.operations.export_gcode import ALLOWED_GCODE_EXTENSIONS  # noqa: E402

_TIER2_METHODS = (
    "get_setting",
    "set_setting",
    "reset_setting",
    "set_layer_height",
    "set_infill_density",
    "set_supports",
    "set_adhesion",
    "set_quality",
    "list_machines",
    "switch_machine",
    "list_materials",
    "switch_material",
    "export_gcode",
)

_KITCHEN_SINK = {
    "key": "layer_height",
    "value": 0.2,
    "mm": 0.2,
    "percent": 20,
    "enabled": True,
    "type": "brim",
    "preset": "normal",
    "name": "x",
    "path": "out.gcode",
}


def test_tier2_methods_registered() -> None:
    for method in _TIER2_METHODS:
        env = router.dispatch(method, dict(_KITCHEN_SINK))
        assert env["ok"] is False  # no live Cura in the harness
        assert "Unknown method" not in env["error"]["message"]


def test_curated_writers_reject_bad_args() -> None:
    with pytest.raises(ValueError):
        settings_op.set_layer_height(0)
    with pytest.raises(ValueError):
        settings_op.set_infill_density(150)
    with pytest.raises(ValueError):
        settings_op.set_supports(True, "sideways")
    with pytest.raises(ValueError):
        settings_op.set_adhesion("glue")


def test_gcode_output_sandbox(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", str(tmp_path))
    accepted = _validate_output_path(str(tmp_path / "out.gcode"), ALLOWED_GCODE_EXTENSIONS)
    assert accepted.suffix == ".gcode"
    # an .stl path is NOT a valid gcode target
    with pytest.raises(InvalidPath):
        _validate_output_path(str(tmp_path / "out.stl"), ALLOWED_GCODE_EXTENSIONS)
    # traversal still rejected
    with pytest.raises(InvalidPath):
        _validate_output_path(str(tmp_path / ".." / "out.gcode"), ALLOWED_GCODE_EXTENSIONS)
    assert os.path.sep  # platform sanity
