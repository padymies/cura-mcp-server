"""Transform operations: rotate, lay_flat, reset_orientation, and the Tier 1
scale / mirror / move / center / scale_to_fit. All marshal to the main thread.
"""
from __future__ import annotations

from ..adapters import cura_api
from ..bridge.main_thread import run_on_main_thread

_VALID_AXES = {"x", "y", "z"}


def rotate(axis: str, degrees: float) -> dict:
    axis = axis.lower()
    if axis not in _VALID_AXES:
        raise ValueError(f"Invalid axis '{axis}'. Use x, y, or z.")
    return run_on_main_thread(lambda: cura_api.apply_rotation(axis, float(degrees)))


def lay_flat() -> dict:
    return run_on_main_thread(cura_api.lay_flat)


def reset_orientation() -> dict:
    return run_on_main_thread(cura_api.reset_orientation)


# --- Tier 1 transforms ----------------------------------------------------

def scale_model(
    node_id: str,
    factor: float | None = None,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
) -> dict:
    """Uniform ``factor`` (multiplies current size) OR per-axis x/y/z multipliers."""
    if factor is not None:
        sx = sy = sz = float(factor)
    else:
        sx = float(x) if x is not None else 1.0
        sy = float(y) if y is not None else 1.0
        sz = float(z) if z is not None else 1.0
    return run_on_main_thread(lambda: cura_api.scale_node(node_id, sx, sy, sz))


def mirror_model(node_id: str, axis: str) -> dict:
    axis = axis.lower()
    if axis not in _VALID_AXES:
        raise ValueError(f"Invalid axis '{axis}'. Use x, y, or z.")
    return run_on_main_thread(lambda: cura_api.mirror_node(node_id, axis))


def move_model(node_id: str, x: float, y: float, z: float, relative: bool = False) -> dict:
    return run_on_main_thread(
        lambda: cura_api.move_node(node_id, float(x), float(y), float(z), bool(relative))
    )


def center_model(node_id: str) -> dict:
    return run_on_main_thread(lambda: cura_api.center_node(node_id))


def scale_to_fit(node_id: str) -> dict:
    return run_on_main_thread(lambda: cura_api.scale_to_fit_node(node_id))
