"""Tier 2 settings validation (no live Cura).

Exercises the guard logic in cura_api.set_setting against a fake container stack:
bad key, per-extruder, out-of-range, and bad enum option are all rejected; a valid
write is applied and re-read. Also covers the pure _coerce_value helper.
"""
from __future__ import annotations

import importlib

import pytest

cura_api = importlib.import_module("cura_plugin.adapters.cura_api")
from cura_plugin.errors import (  # noqa: E402 - after package registration
    InvalidSettingValue,
    PerExtruderUnsupported,
    UnknownSetting,
)


# --- pure coercion --------------------------------------------------------

def test_coerce_scalars() -> None:
    assert cura_api._coerce_value("float", "0.2") == 0.2
    assert cura_api._coerce_value("int", "5") == 5
    assert cura_api._coerce_value("int", 5.0) == 5
    assert cura_api._coerce_value("bool", "true") is True
    assert cura_api._coerce_value("bool", "off") is False
    assert cura_api._coerce_value("enum", "brim") == "brim"


def test_coerce_bad_value_raises() -> None:
    with pytest.raises(InvalidSettingValue):
        cura_api._coerce_value("float", "not-a-number")


# --- fake stack -----------------------------------------------------------

class _UserChanges:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def removeInstance(self, key: str) -> None:  # noqa: N802 - mirror Cura API
        self.removed.append(key)


class _FakeStack:
    def __init__(self, props: dict, exists: bool = True) -> None:
        self._props = props
        self._exists = exists
        self.written: dict = {}
        self.userChanges = _UserChanges()

    @property
    def definition(self):  # noqa: ANN202
        exists = self._exists

        class _Def:
            def findDefinitions(self, key: str | None = None) -> list:  # noqa: N802
                return [object()] if exists else []

        return _Def()

    def getProperty(self, key: str, prop: str):  # noqa: ANN201
        if prop == "value" and key in self.written:
            return self.written[key]
        return self._props.get(prop)

    def setProperty(self, key: str, prop: str, value) -> None:  # noqa: ANN001
        if prop == "value":
            self.written[key] = value


def _use(monkeypatch, stack) -> None:  # noqa: ANN001
    class _App:
        def getGlobalContainerStack(self):  # noqa: N802, ANN202
            return stack

    monkeypatch.setattr(cura_api, "get_application", lambda: _App())


_FLOAT = {"type": "float", "minimum_value": 0.04, "maximum_value": 1.0, "unit": "mm"}


def test_set_unknown_key_rejected(monkeypatch) -> None:
    _use(monkeypatch, _FakeStack(_FLOAT, exists=False))
    with pytest.raises(UnknownSetting):
        cura_api.set_setting("nope", 0.2)


def test_set_per_extruder_without_extruder_rejected(monkeypatch) -> None:
    # Per-extruder key + no active extruder available (the harness has no Cura) ->
    # refuse rather than write to the wrong container. Value is in range so it
    # reaches the routing step. (Live, it routes to the active extruder instead.)
    _use(monkeypatch, _FakeStack({**_FLOAT, "settable_per_extruder": True}))
    with pytest.raises(PerExtruderUnsupported):
        cura_api.set_setting("layer_height", 0.2)


def test_set_out_of_range_rejected(monkeypatch) -> None:
    _use(monkeypatch, _FakeStack(_FLOAT))
    with pytest.raises(InvalidSettingValue):
        cura_api.set_setting("layer_height", 5.0)  # > max 1.0
    with pytest.raises(InvalidSettingValue):
        cura_api.set_setting("layer_height", 0.0)  # < min 0.04


def test_set_bad_enum_option_rejected(monkeypatch) -> None:
    enum_props = {"type": "enum", "options": {"skirt": "Skirt", "brim": "Brim"}}
    _use(monkeypatch, _FakeStack(enum_props))
    with pytest.raises(InvalidSettingValue):
        cura_api.set_setting("adhesion_type", "raft")


def test_set_valid_applies_and_rereads(monkeypatch) -> None:
    stack = _FakeStack(_FLOAT)
    _use(monkeypatch, stack)
    out = cura_api.set_setting("layer_height", "0.2")  # string coerces to float
    assert out["value"] == 0.2
    assert stack.written["layer_height"] == 0.2


def test_get_unknown_key_rejected(monkeypatch) -> None:
    _use(monkeypatch, _FakeStack(_FLOAT, exists=False))
    with pytest.raises(UnknownSetting):
        cura_api.get_setting("nope")


def test_reset_removes_override(monkeypatch) -> None:
    stack = _FakeStack(_FLOAT)
    _use(monkeypatch, stack)
    cura_api.reset_setting("layer_height")
    assert "layer_height" in stack.userChanges.removed
