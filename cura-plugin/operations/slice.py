"""slice operation: trigger a slice and block until the backend settles.

This is the core engineering of the plugin. CuraEngine slices asynchronously;
PrintInformation only becomes valid once the slice reaches a terminal state. We
make ``slice`` synchronous from the caller's view:

  1. On the main thread, subscribe a one-shot-ish listener to the backend state
     signal, then force a fresh slice.
  2. The worker thread blocks on a ``threading.Event`` until the listener reports
     a terminal state (DONE / ERROR / DISABLED), or the timeout elapses.
  3. Debounce: a prior ``rotate`` may have queued a re-slice, so intermediate
     SLICING churn is ignored; we only latch on a terminal state observed AFTER
     we forced the slice.
  4. Always unsubscribe.

The version-sensitive wiring (which signal, state mapping, forceSlice) lives in
adapters.cura_api; this file is pure orchestration and is therefore stable.
"""
from __future__ import annotations

import threading

from ..adapters import cura_api
from ..adapters.cura_api import SliceState
from ..bridge.main_thread import run_on_main_thread
from ..errors import SliceFailed, SliceTimeout

_TERMINAL = {SliceState.DONE, SliceState.ERROR, SliceState.DISABLED}


def run_slice(timeout: float = 300.0) -> dict:
    # Nothing-printable guard: with no model INSIDE the build volume — an empty
    # plate, or every model pushed outside it — CuraEngine never emits a terminal
    # backend transition, so the subscribe/forceSlice/wait handshake would block
    # until `timeout` (a 5-minute hang on paths an agent will hit: clear→slice, or
    # move/scale a model off the plate→slice). Short-circuit to the structured
    # `disabled` result (FR-5) instead.
    if run_on_main_thread(cura_api.count_printable_nodes) == 0:
        return {
            "state": "disabled",
            "detail": "No printable model on the plate (it's empty, or all models are "
            "outside the build volume).",
        }

    settled = threading.Event()
    outcome: dict[str, SliceState] = {}
    seen = {"processing": False}

    def on_state(state: SliceState) -> None:
        # Runs on the main thread (signal context).
        if state is SliceState.SLICING:
            seen["processing"] = True
            return
        if "state" in outcome:
            return
        # Debounce the stale-Done race: an in-flight auto-reslice from a prior
        # `rotate` can emit Done right after we subscribe but before our forced
        # slice spins up. Backend.setState only emits on transitions, and a real
        # forced slice always passes through Processing (forceSlice ->
        # markSliceAll + slice), so ignore a Done until Processing was observed.
        # ERROR / DISABLED are latched immediately: DISABLED (model outside the
        # build volume) may never be preceded by Processing, and must still
        # return a structured result instead of timing out (FR-5).
        if state is SliceState.DONE and not seen["processing"]:
            return
        if state in _TERMINAL:
            outcome["state"] = state
            settled.set()

    def _setup() -> object:
        token = cura_api.subscribe_backend_state(on_state)
        cura_api.start_slice()  # force a fresh slice AFTER subscribing
        return token

    token = run_on_main_thread(_setup)
    try:
        if not settled.wait(timeout):
            raise SliceTimeout(f"Slice did not settle within {timeout:.0f}s.")
        state = outcome["state"]
    finally:
        run_on_main_thread(lambda: cura_api.unsubscribe_backend_state(token))

    if state is SliceState.ERROR:
        raise SliceFailed("Slicing failed. Check the model and slicing settings.")
    if state is SliceState.DISABLED:
        return {"state": "disabled", "detail": "Nothing to slice (model outside build volume?)."}
    return {"state": "done", "detail": None}
