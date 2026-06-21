"""get_status operation: report active profile + plugin version.

Also doubles as the live API-surface smoke check (see tasks Phase 3): if the
adapter calls here fail, the API has drifted and should be flagged.
"""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread


def get_status() -> dict:
    def _read() -> dict:
        machine, material = cura_api.get_active_machine_material()
        return {"active_machine": machine, "active_material": material}

    data = run_on_main_thread(_read)
    data["plugin_version"] = cura_api.get_plugin_version()
    return data
