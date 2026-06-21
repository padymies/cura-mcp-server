"""Output-path sandbox for export_model (no live Cura).

The write path must pass the same allow-list / no-traversal / allowed-extension
checks as load_model's input path. Unlike the input sandbox, the target file need
not exist yet — but its parent directory must, and it must sit inside an allowed
root. See docs/security-model.md.
"""
from __future__ import annotations

import importlib
import os

import pytest

export = importlib.import_module("cura_plugin.operations.export")
from cura_plugin.errors import InvalidPath  # noqa: E402 - after package registration


def _set_roots(monkeypatch, *dirs) -> None:  # noqa: ANN001
    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", os.pathsep.join(str(d) for d in dirs))


def test_output_accepts_new_stl_in_allowed_dir(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    target = tmp_path / "out.stl"  # does not exist yet
    resolved = export._validate_output_path(str(target))
    assert resolved.suffix == ".stl"
    assert str(resolved).startswith(str(tmp_path.resolve()))


def test_output_accepts_3mf(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    assert export._validate_output_path(str(tmp_path / "out.3mf")).suffix == ".3mf"


def test_output_rejects_bad_extension(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    with pytest.raises(InvalidPath):
        export._validate_output_path(str(tmp_path / "out.gcode"))


def test_output_rejects_traversal(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    with pytest.raises(InvalidPath):
        export._validate_output_path(str(tmp_path / ".." / "out.stl"))


def test_output_rejects_outside_roots(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    _set_roots(monkeypatch, allowed)
    with pytest.raises(InvalidPath):
        export._validate_output_path(str(outside / "out.stl"))


def test_output_rejects_missing_parent_dir(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    with pytest.raises(InvalidPath):
        export._validate_output_path(str(tmp_path / "nope" / "out.stl"))


def test_output_rejects_empty(monkeypatch) -> None:  # noqa: ANN001
    with pytest.raises(InvalidPath):
        export._validate_output_path("")
