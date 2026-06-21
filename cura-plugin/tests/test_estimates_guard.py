"""Estimates guard: get_estimates gates on the current backend state.

Without a completed slice it must return honest zeros + valid:false (NEVER raw
PrintInformation / negative time); after a DONE slice it returns the real values.
The duration helper clamps negatives as belt-and-suspenders. No live Cura needed.
"""
from __future__ import annotations

import importlib

est_mod = importlib.import_module("cura_plugin.operations.estimate")
cura_api = est_mod.cura_api
SliceState = cura_api.SliceState


def test_estimates_not_done_returns_valid_false_zeros(monkeypatch) -> None:
    monkeypatch.setattr(est_mod, "run_on_main_thread", lambda fn: fn())
    monkeypatch.setattr(cura_api, "get_backend_state", lambda: SliceState.NOT_STARTED)

    def _fail_read() -> dict:
        raise AssertionError("must not read PrintInformation when backend is not DONE")

    monkeypatch.setattr(cura_api, "read_print_information", _fail_read)
    monkeypatch.setattr(cura_api, "get_active_machine_material", lambda: ("Ender", "PLA"))

    r = est_mod.get_estimates()

    assert r["valid"] is False
    assert r["extruders"] == []
    assert r["total_weight_g"] == 0.0
    assert r["total_length_m"] == 0.0
    assert r["print_time_seconds"] == 0
    assert "current state: not_started" in r["note"]


def test_estimates_done_returns_real_values(monkeypatch) -> None:
    monkeypatch.setattr(est_mod, "run_on_main_thread", lambda fn: fn())
    monkeypatch.setattr(cura_api, "get_backend_state", lambda: SliceState.DONE)
    monkeypatch.setattr(cura_api, "get_active_machine_material", lambda: ("Ender", "PLA"))
    monkeypatch.setattr(
        cura_api,
        "read_print_information",
        lambda: {
            "extruders": [{"weight_g": 15.0, "length_m": 5.0, "cost": None}],
            "total_weight_g": 15.0,
            "total_length_m": 5.0,
            "print_time_seconds": 5973,
        },
    )

    r = est_mod.get_estimates()

    assert r["valid"] is True
    assert r["note"] is None
    assert r["print_time_seconds"] == 5973
    assert r["total_weight_g"] == 15.0
    assert r["profile_warning"] is None


def test_duration_to_seconds_never_negative() -> None:
    class _Dur:
        days = 0
        hours = -25
        minutes = 0
        seconds = -61

    assert cura_api._duration_to_seconds(_Dur()) == 0
    assert cura_api._duration_to_seconds(None) == 0
