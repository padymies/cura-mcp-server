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
    load,
    machine,
    models,
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
