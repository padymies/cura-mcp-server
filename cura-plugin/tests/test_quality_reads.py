"""v0.5 quality-profile reads: router registration + active/note logic (no live Cura).

Registration mirrors test_tier3 (dispatch must not return "Unknown method"). The
active-flag and custom-profile note are pure logic over the adapter's Cura
accessors, so we unit-test them by stubbing those accessors — no Qt / live Cura.
"""
from __future__ import annotations

import importlib

router = importlib.import_module("cura_plugin.server.router")
cura_api = importlib.import_module("cura_plugin.adapters.cura_api")


def test_quality_read_methods_registered() -> None:
    for method in ("list_quality_profiles", "get_quality"):
        env = router.dispatch(method, {})
        assert env["ok"] is False  # no live Cura in the harness
        assert "Unknown method" not in env["error"]["message"]


class _FakeGroup:
    def __init__(self, name: str) -> None:
        self._name = name

    def getName(self) -> str:  # noqa: N802 - mirror Cura's QualityGroup API
        return self._name


class _FakeMachineManager:
    def __init__(self, active_qt: str, custom: bool = False, custom_name: str = "") -> None:
        self.activeQualityType = active_qt
        self.hasCustomQuality = custom
        self.activeQualityOrQualityChangesName = custom_name


class _FakeApp:
    def __init__(self, mm: _FakeMachineManager) -> None:
        self._mm = mm

    def getMachineManager(self) -> _FakeMachineManager:  # noqa: N802 - mirror Cura API
        return self._mm


def _patch(monkeypatch, groups: dict, mm: _FakeMachineManager) -> None:  # noqa: ANN001
    monkeypatch.setattr(cura_api, "_available_quality_groups", lambda: groups)
    monkeypatch.setattr(cura_api, "get_application", lambda: _FakeApp(mm))


def test_list_quality_profiles_marks_single_active(monkeypatch) -> None:  # noqa: ANN001
    groups = {
        "low": _FakeGroup("Low"),
        "standard": _FakeGroup("Standard"),
        "super": _FakeGroup("Super"),
    }
    _patch(monkeypatch, groups, _FakeMachineManager("standard"))

    out = cura_api.list_quality_profiles()
    by_type = {p["quality_type"]: p for p in out["profiles"]}

    assert by_type["standard"]["active"] is True
    assert by_type["standard"]["name"] == "Standard"
    assert by_type["low"]["active"] is False
    assert sum(p["active"] for p in out["profiles"]) == 1


def test_get_quality_plain(monkeypatch) -> None:  # noqa: ANN001
    _patch(monkeypatch, {}, _FakeMachineManager("super"))
    assert cura_api.get_quality() == {"key": "quality", "value": "super", "type": "enum"}


def test_get_quality_custom_adds_note(monkeypatch) -> None:  # noqa: ANN001
    _patch(monkeypatch, {}, _FakeMachineManager("standard", custom=True, custom_name="My Custom"))
    out = cura_api.get_quality()

    assert out["value"] == "standard"
    assert "My Custom" in out["note"]
