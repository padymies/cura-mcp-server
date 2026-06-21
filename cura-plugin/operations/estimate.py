"""get_estimates operation: read material/time from the last successful slice.

Warns when no machine/material profile is active, because material weight is
derived from the active material's density and is otherwise meaningless.
"""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def get_estimates() -> dict:
    def _read() -> dict:
        # Gate on the CURRENT backend state: PrintInformation is only valid after a
        # completed slice. Read out of order (before slicing, mid-slice, or after a
        # rotate invalidated the last slice) it returns stale/garbage values
        # (observed print_time_seconds = -90061). Return honest zeros + valid:false
        # instead of a misleading number.
        state = cura_api.get_backend_state()
        if state is not cura_api.SliceState.DONE:
            return {
                "extruders": [],
                "total_weight_g": 0.0,
                "total_length_m": 0.0,
                "print_time_seconds": 0,
                "valid": False,
                "note": f"No completed slice. Run slice first (current state: {state.value}).",
                "profile_warning": None,
            }

        machine, material = cura_api.get_active_machine_material()
        data = cura_api.read_print_information()
        time_seconds = int(data.get("print_time_seconds", 0))
        extruders = data.get("extruders", [])
        result = {
            "extruders": extruders,
            "total_weight_g": data.get("total_weight_g", 0.0),
            "total_length_m": data.get("total_length_m", 0.0),
            "print_time_seconds": time_seconds,
            "valid": True,
            "note": None,
            "profile_warning": None,
        }
        if not machine or not material:
            result["profile_warning"] = (
                "No active machine/material profile; weight and cost estimates "
                "may be unreliable."
            )
        return result

    return run_on_main_thread(_read)
