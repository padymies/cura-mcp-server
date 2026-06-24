"""Map RPC method names to plugin operations and shape the response envelope.

Keeps the operations decoupled from HTTP. Errors are converted to the structured
{ok: false, error: {code, message}} envelope the bridge expects.
"""
from __future__ import annotations

from typing import Any, Callable

from ..errors import PluginError
from ..operations import (
    clear,
    estimate,
    export,
    export_gcode,
    group,
    load,
    machine,
    models,
    profiles,
    project,
    settings,
    snapshot,
    status,
    transform,
)
from ..operations import slice as slice_op

# method name -> callable(params: dict) -> data: dict
_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "get_status": lambda p: status.get_status(),
    "load_model": lambda p: load.load_model(p["path"]),
    "clear_plate": lambda p: clear.clear_plate(),
    "rotate": lambda p: transform.rotate(p["axis"], p["degrees"]),
    "lay_flat": lambda p: transform.lay_flat(),
    "reset_orientation": lambda p: transform.reset_orientation(),
    "slice": lambda p: slice_op.run_slice(),
    "get_estimates": lambda p: estimate.get_estimates(),
    # Tier 1 — model management
    "list_models": lambda p: models.list_models(),
    "select_model": lambda p: models.select_model(p["node_id"]),
    "remove_model": lambda p: models.remove_model(p["node_id"]),
    "duplicate_model": lambda p: models.duplicate_model(p["node_id"], p.get("count", 1)),
    "arrange_all": lambda p: models.arrange_all(),
    # Tier 1 — transforms
    "scale_model": lambda p: transform.scale_model(
        p["node_id"], p.get("factor"), p.get("x"), p.get("y"), p.get("z")
    ),
    "mirror_model": lambda p: transform.mirror_model(p["node_id"], p["axis"]),
    "move_model": lambda p: transform.move_model(
        p["node_id"], p.get("x", 0.0), p.get("y", 0.0), p.get("z", 0.0), p.get("relative", False)
    ),
    "center_model": lambda p: transform.center_model(p["node_id"]),
    "scale_to_fit": lambda p: transform.scale_to_fit(p["node_id"]),
    # Tier 1 — visibility / info / export
    "get_machine_info": lambda p: machine.get_machine_info(),
    "get_snapshot": lambda p: snapshot.get_snapshot(p.get("width", 600), p.get("height", 600)),
    "export_model": lambda p: export.export_model(
        p.get("target", "all"), p["path"], p.get("format", "stl")
    ),
    # Tier 2 — settings
    "get_setting": lambda p: settings.get_setting(p["key"]),
    "set_setting": lambda p: settings.set_setting(p["key"], p["value"]),
    "reset_setting": lambda p: settings.reset_setting(p["key"]),
    # Tier 2 — curated writers
    "set_layer_height": lambda p: settings.set_layer_height(p["mm"]),
    "set_infill_density": lambda p: settings.set_infill_density(p["percent"]),
    "set_supports": lambda p: settings.set_supports(p["enabled"], p.get("type")),
    "set_adhesion": lambda p: settings.set_adhesion(p["type"]),
    "set_quality": lambda p: settings.set_quality(p["preset"]),
    # Tier 2 — profiles
    "list_machines": lambda p: profiles.list_machines(),
    "switch_machine": lambda p: profiles.switch_machine(p["name"]),
    "list_materials": lambda p: profiles.list_materials(),
    "switch_material": lambda p: profiles.switch_material(p["name"]),
    # Tier 2 — export gcode
    "export_gcode": lambda p: export_gcode.export_gcode(p["path"]),
    # Tier 3 (M1) — settings introspection + bulk reset
    "get_all_user_settings": lambda p: settings.get_all_user_settings(),
    "reset_all_settings": lambda p: settings.reset_all_settings(),
    # Tier 3 (M1) — nozzle variants
    "list_variants": lambda p: profiles.list_variants(),
    "switch_variant": lambda p: profiles.switch_variant(p["name"]),
    # Tier 3 (M2) — group / ungroup / merge
    "group_models": lambda p: group.group_models(p["node_ids"]),
    "ungroup_model": lambda p: group.ungroup_model(p["node_id"]),
    "merge_models": lambda p: group.merge_models(p["node_ids"]),
    # Tier 3 (M3) — project save / open
    "save_project": lambda p: project.save_project(p["path"]),
    "open_project": lambda p: project.open_project(
        p["path"], p.get("confirm", False), p.get("mode", "create_new")
    ),
    # Tier 3 (M4) — per-object settings & mesh types
    "set_model_setting": lambda p: settings.set_model_setting(p["node_id"], p["key"], p["value"]),
    "reset_model_setting": lambda p: settings.reset_model_setting(p["node_id"], p["key"]),
    "set_mesh_type": lambda p: settings.set_mesh_type(p["node_id"], p["type"]),
    "get_model_settings": lambda p: settings.get_model_settings(p["node_id"]),
}


def dispatch(method: str, params: dict) -> dict:
    """Return the response envelope for a method call. Never raises."""
    handler = _HANDLERS.get(method)
    if handler is None:
        return _error("cura_mcp_error", f"Unknown method: {method}")
    try:
        data = handler(params or {})
        return {"ok": True, "data": data, "error": None}
    except PluginError as exc:
        return _error(exc.code, str(exc))
    except KeyError as exc:
        return _error("cura_mcp_error", f"Missing parameter: {exc}")
    except NotImplementedError:
        return _error("cura_mcp_error", f"'{method}' not yet implemented in the adapter.")
    except Exception as exc:  # noqa: BLE001 - last resort; never leak a stack trace
        return _error("cura_mcp_error", f"Internal error: {exc}")


def _error(code: str, message: str) -> dict:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}
