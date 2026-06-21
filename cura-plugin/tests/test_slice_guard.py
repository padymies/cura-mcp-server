"""Empty-plate guard for run_slice.

With zero sliceable nodes the handshake would block until the timeout, so
``run_slice`` must short-circuit to a structured ``disabled`` result WITHOUT
subscribing to the backend or calling forceSlice. With nodes present, the guard
passes and the handshake is entered as normal. No live Cura needed (the adapter
calls are mocked).
"""
from __future__ import annotations

import importlib

import pytest

slice_mod = importlib.import_module("cura_plugin.operations.slice")


def test_empty_plate_returns_disabled_without_handshake(monkeypatch) -> None:
    monkeypatch.setattr(slice_mod, "run_on_main_thread", lambda fn: fn())
    monkeypatch.setattr(slice_mod.cura_api, "count_printable_nodes", lambda: 0)

    def _fail_subscribe(*a: object, **k: object) -> None:
        raise AssertionError("must not subscribe to the backend on an empty plate")

    def _fail_start(*a: object, **k: object) -> None:
        raise AssertionError("must not call forceSlice on an empty plate")

    monkeypatch.setattr(slice_mod.cura_api, "subscribe_backend_state", _fail_subscribe)
    monkeypatch.setattr(slice_mod.cura_api, "start_slice", _fail_start)

    result = slice_mod.run_slice()

    assert result["state"] == "disabled"
    assert "outside the build volume" in result["detail"]


def test_nonempty_plate_passes_guard_into_handshake(monkeypatch) -> None:
    # With a sliceable node present the guard must NOT short-circuit; the handshake
    # setup is reached (proven by the subscribe call firing).
    monkeypatch.setattr(slice_mod, "run_on_main_thread", lambda fn: fn())
    monkeypatch.setattr(slice_mod.cura_api, "count_printable_nodes", lambda: 1)

    class _Entered(Exception):
        pass

    def _subscribe(*a: object, **k: object) -> None:
        raise _Entered

    monkeypatch.setattr(slice_mod.cura_api, "subscribe_backend_state", _subscribe)

    with pytest.raises(_Entered):
        slice_mod.run_slice()
