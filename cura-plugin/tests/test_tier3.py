"""Tier 3 router registration (no live Cura).

The adapter calls are validated manually (docs/manual-smoke-test.md §9); here we
only assert every Tier 3 method is wired into the router so a typo can't silently
drop a tool. Without a live Cura the handlers fail inside the adapter, which the
router converts to ok:False — but never to an "Unknown method" envelope.
"""
from __future__ import annotations

import importlib
import types

import pytest

router = importlib.import_module("cura_plugin.server.router")
group_op = importlib.import_module("cura_plugin.operations.group")
project_op = importlib.import_module("cura_plugin.operations.project")
cura_api = importlib.import_module("cura_plugin.adapters.cura_api")
from cura_plugin.errors import (  # noqa: E402 - after pkg register
    InvalidPath,
    InvalidSettingValue,
    LoadFailed,
)

_TIER3_METHODS = (
    # M1 — settings introspection + variants
    "get_all_user_settings",
    "reset_all_settings",
    "list_variants",
    "switch_variant",
    # M2 — group / ungroup / merge
    "group_models",
    "ungroup_model",
    "merge_models",
    # M3 — project save / open
    "save_project",
    "open_project",
    # M4 — per-object settings & mesh types
    "set_model_setting",
    "reset_model_setting",
    "set_mesh_type",
    "get_model_settings",
)

_KITCHEN_SINK = {
    "name": "AA 0.4",
    "node_id": "Cube",
    "node_ids": ["Cube", "Cube (1)"],
    "path": "project.3mf",
    "key": "infill_sparse_density",
    "value": 25,
    "type": "support_mesh",
}


def test_tier3_methods_registered() -> None:
    for method in _TIER3_METHODS:
        env = router.dispatch(method, dict(_KITCHEN_SINK))
        assert env["ok"] is False  # no live Cura in the harness
        assert "Unknown method" not in env["error"]["message"]


def test_group_merge_reject_too_few_ids() -> None:
    with pytest.raises(ValueError):
        group_op.group_models(["only-one"])
    with pytest.raises(ValueError):
        group_op.merge_models([])


def test_save_project_sandbox_is_3mf_only(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", str(tmp_path))
    # a .3mf inside the sandbox is accepted (validation happens before any Cura call)
    from cura_plugin.operations.export import _validate_output_path

    accepted = _validate_output_path(str(tmp_path / "proj.3mf"), project_op._PROJECT_EXTENSIONS)
    assert accepted.suffix == ".3mf"
    # a project must be a .3mf — an .stl name is rejected so bytes match the name
    with pytest.raises(InvalidPath):
        _validate_output_path(str(tmp_path / "proj.stl"), project_op._PROJECT_EXTENSIONS)
    # traversal still rejected
    with pytest.raises(InvalidPath):
        _validate_output_path(str(tmp_path / ".." / "proj.3mf"), project_op._PROJECT_EXTENSIONS)


def _fake_cura_api(calls: list) -> types.SimpleNamespace:
    """A stand-in for the adapter that records which workspace call ran."""
    return types.SimpleNamespace(
        workspace_summary=lambda: {"machine": "Printer A", "models": 3},
        preview_project_workspace=lambda p: (
            calls.append(("preview", p)) or {"valid_project": True, "name": "proj"}
        ),
        open_project_workspace=lambda p, m: (
            calls.append(("open", p, m)) or {"name": "proj", "models": 1, "note": "opened"}
        ),
    )


def test_open_project_preview_does_not_mutate(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """confirm=False must run the non-destructive preview and never call open."""
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", str(tmp_path))
    proj = tmp_path / "p.3mf"
    proj.write_bytes(b"PK\x03\x04")  # exists with a .3mf suffix (content unread)
    calls: list = []
    monkeypatch.setattr(project_op, "run_on_main_thread", lambda fn, *a, **k: fn())
    monkeypatch.setattr(project_op, "cura_api", _fake_cura_api(calls))

    out = project_op.open_project(str(proj), confirm=False, mode="create_new")
    assert out["applied"] is False
    assert out["machine"] is None and out["models"] is None
    assert out["previous_machine"] == "Printer A" and out["previous_models"] == 3
    # The preview ran; the destructive open never did.
    assert ("preview", str(proj)) in calls
    assert all(c[0] != "open" for c in calls)


def test_open_project_confirm_executes(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", str(tmp_path))
    proj = tmp_path / "p.3mf"
    proj.write_bytes(b"PK\x03\x04")
    calls: list = []
    monkeypatch.setattr(project_op, "run_on_main_thread", lambda fn, *a, **k: fn())
    monkeypatch.setattr(project_op, "cura_api", _fake_cura_api(calls))

    out = project_op.open_project(str(proj), confirm=True, mode="create_new")
    assert out["applied"] is True
    assert out["models"] == 1
    assert any(c[0] == "open" and c[2] == "create_new" for c in calls)


def test_open_project_rejects_unknown_mode(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", str(tmp_path))
    proj = tmp_path / "p.3mf"
    proj.write_bytes(b"PK\x03\x04")
    with pytest.raises(LoadFailed):
        project_op.open_project(str(proj), confirm=True, mode="bogus")


def test_replace_active_is_fail_closed() -> None:
    # The mode guard runs before any Cura access, so this is testable headlessly:
    # replace_active is wired but must refuse (LoadFailed) until source-verified.
    with pytest.raises(LoadFailed):
        cura_api.open_project_workspace("whatever.3mf", "replace_active")
    # an outright unknown mode is also refused before touching Cura
    with pytest.raises(LoadFailed):
        cura_api.open_project_workspace("whatever.3mf", "nonsense")


def _write_min_3mf(path, n_items: int) -> None:  # noqa: ANN001
    """Write a minimal 3MF whose core model part has ``n_items`` <build><item>s."""
    import zipfile

    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    objects = "".join(f'<object id="{i}" type="model"/>' for i in range(1, n_items + 1))
    items = "".join(f'<item objectid="{i}"/>' for i in range(1, n_items + 1))
    model = (
        f'<?xml version="1.0"?><model xmlns="{ns}"><resources>{objects}</resources>'
        f"<build>{items}</build></model>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("3D/3dmodel.model", model)


def test_count_project_models_reads_build_items(tmp_path) -> None:  # noqa: ANN001
    # version-independent count straight from the .3mf (the open's count source).
    p1 = tmp_path / "one.3mf"
    _write_min_3mf(p1, 1)
    assert cura_api._count_project_models(str(p1)) == 1
    p3 = tmp_path / "three.3mf"
    _write_min_3mf(p3, 3)
    assert cura_api._count_project_models(str(p3)) == 3
    # a non-zip / unparseable file returns None so the caller can fall back
    bad = tmp_path / "bad.3mf"
    bad.write_bytes(b"not a zip")
    assert cura_api._count_project_models(str(bad)) is None


def test_set_mesh_type_rejects_invalid_type() -> None:
    # mesh-type validation is pure Python and runs before any Cura access.
    with pytest.raises(InvalidSettingValue):
        cura_api.set_mesh_type("Cube", "bogus_mesh")
    # the allowed set is exactly the five documented roles
    assert cura_api._MESH_TYPES == {
        "normal",
        "support_mesh",
        "anti_overhang_mesh",
        "infill_mesh",
        "cutting_mesh",
    }
