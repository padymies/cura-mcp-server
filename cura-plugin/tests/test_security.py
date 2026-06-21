"""Unit tests for the security controls that need no live Cura.

Covers the per-session token + Host allow-list (auth.py) and the load_model path
sandbox (operations/load.py). See docs/security-model.md.
"""
from __future__ import annotations

import importlib

import pytest

auth = importlib.import_module("cura_plugin.server.auth")
load = importlib.import_module("cura_plugin.operations.load")
from cura_plugin.errors import InvalidPath  # noqa: E402 - after package registration


# --- auth: token -----------------------------------------------------------

def test_token_roundtrip_and_rejects_wrong(tmp_path) -> None:  # noqa: ANN001
    mgr = auth.TokenManager(token_file=tmp_path / "token")
    mgr.write()
    assert (tmp_path / "token").read_text(encoding="utf-8") == mgr.token
    assert mgr.check_token(mgr.token) is True
    assert mgr.check_token("wrong") is False
    assert mgr.check_token(None) is False
    assert mgr.check_token("") is False


def test_token_cleanup_removes_file(tmp_path) -> None:  # noqa: ANN001
    mgr = auth.TokenManager(token_file=tmp_path / "token")
    mgr.write()
    mgr.cleanup()
    assert not (tmp_path / "token").exists()


# --- auth: Host allow-list -------------------------------------------------

@pytest.mark.parametrize(
    "host,allowed",
    [
        ("127.0.0.1", True),
        ("127.0.0.1:8765", True),
        ("localhost", True),
        ("localhost:8765", True),
        ("evil.example.com", False),
        ("0.0.0.0", False),
        ("", False),
        (None, False),
    ],
)
def test_host_allowed(host, allowed) -> None:  # noqa: ANN001
    assert auth.host_allowed(host) is allowed


# --- load_model path sandbox ----------------------------------------------

def _set_roots(monkeypatch, *dirs) -> None:  # noqa: ANN001
    import os

    monkeypatch.setenv("CURA_MCP_ALLOWED_DIRS", os.pathsep.join(str(d) for d in dirs))


def test_sandbox_accepts_allowed_stl(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    model = tmp_path / "part.stl"
    model.write_text("solid", encoding="utf-8")
    resolved = load._validate_path(str(model))
    assert resolved == model.resolve()


def test_sandbox_rejects_disallowed_extension(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    bad = tmp_path / "part.txt"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(InvalidPath):
        load._validate_path(str(bad))


def test_sandbox_rejects_traversal(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _set_roots(monkeypatch, tmp_path)
    with pytest.raises(InvalidPath):
        load._validate_path(str(tmp_path / ".." / "part.stl"))


def test_sandbox_rejects_outside_roots(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    _set_roots(monkeypatch, allowed)
    intruder = outside / "part.stl"
    intruder.write_text("solid", encoding="utf-8")
    with pytest.raises(InvalidPath):
        load._validate_path(str(intruder))


def test_sandbox_rejects_empty_path(monkeypatch) -> None:  # noqa: ANN001
    with pytest.raises(InvalidPath):
        load._validate_path("")


def test_allowed_roots_env_override_skips_missing(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    import os

    real = tmp_path / "real"
    real.mkdir()
    monkeypatch.setenv(
        "CURA_MCP_ALLOWED_DIRS", os.pathsep.join([str(real), str(tmp_path / "ghost")])
    )
    roots = load._allowed_roots()
    assert real.resolve() in roots
    assert all(r.exists() for r in roots)
