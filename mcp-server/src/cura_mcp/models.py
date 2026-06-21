"""Pydantic models: the tool I/O surface and the plugin request/response contract.

These shapes are the versioned contract between the bridge and the plugin. The
plugin's ``router.py`` validates the same shapes on its side — keep them in sync.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# --- shared ---------------------------------------------------------------

class Axis(str, Enum):
    x = "x"
    y = "y"
    z = "z"


class PluginError(BaseModel):
    code: str
    message: str


class PluginResponse(BaseModel):
    """Envelope returned by every plugin endpoint."""

    ok: bool
    data: dict[str, Any] | None = None
    error: PluginError | None = None


# --- tool inputs ----------------------------------------------------------

class LoadModelInput(BaseModel):
    path: str = Field(..., description="Absolute path to an .stl, .3mf, or .obj file.")


class RotateInput(BaseModel):
    axis: Axis
    degrees: float = Field(..., description="Rotation in degrees, applied about the axis.")


# --- tool outputs ---------------------------------------------------------

class StatusOutput(BaseModel):
    cura_connected: bool
    plugin_version: str | None = None
    active_machine: str | None = None
    active_material: str | None = None
    last_slice_state: str | None = None


class LoadModelOutput(BaseModel):
    node_id: str
    fits_build_volume: bool
    bounds_mm: list[float] = Field(default_factory=list, description="[x, y, z] bounding box")


class ClearPlateOutput(BaseModel):
    cleared: int = Field(..., description="Number of printable models removed from the plate.")


class OrientationOutput(BaseModel):
    node_id: str
    rotation_deg: dict[str, float] = Field(default_factory=dict)


class SliceOutput(BaseModel):
    state: str = Field(..., description="done | error | disabled")
    detail: str | None = None


class ExtruderEstimate(BaseModel):
    weight_g: float
    length_m: float
    cost: float | None = None


class EstimatesOutput(BaseModel):
    extruders: list[ExtruderEstimate]
    total_weight_g: float
    total_length_m: float
    print_time_seconds: int
    valid: bool = Field(
        default=True,
        description="False when there is no completed slice; the figures are then zeros.",
    )
    note: str | None = Field(
        default=None,
        description="Set when valid is False, explaining why (e.g. no slice yet).",
    )
    profile_warning: str | None = Field(
        default=None,
        description="Set when no active machine/material profile makes estimates unreliable.",
    )


# --- Tier 1: model management --------------------------------------------

class ModelInfo(BaseModel):
    node_id: str
    bounds_mm: list[float] = Field(default_factory=list, description="[x, y, z] bounding box")
    position_mm: list[float] = Field(default_factory=list, description="[x, y, z] node origin")


class ListModelsOutput(BaseModel):
    models: list[ModelInfo]


class SelectModelOutput(BaseModel):
    node_id: str
    selected: bool


class RemoveModelOutput(BaseModel):
    removed: str = Field(..., description="node_id of the removed model")


class DuplicateModelOutput(BaseModel):
    original: str
    created: list[str] = Field(default_factory=list, description="node_ids of the new copies")
    count: int


class ArrangeAllOutput(BaseModel):
    arranged: int = Field(..., description="Number of models auto-arranged on the plate.")


class TransformOutput(BaseModel):
    """Result of a scale/mirror/move/center/scale_to_fit on one model."""

    node_id: str
    bounds_mm: list[float] = Field(default_factory=list, description="[x, y, z] bounding box")
    position_mm: list[float] = Field(default_factory=list, description="[x, y, z] node origin")
    fits_build_volume: bool = True


# --- Tier 1: machine info / export ----------------------------------------

class BuildVolumeDims(BaseModel):
    width: float = Field(..., description="X bed size (mm)")
    depth: float = Field(..., description="Y bed size, front-back (mm)")
    height: float = Field(..., description="Z print height (mm)")


class MachineInfoOutput(BaseModel):
    machine_name: str | None
    build_volume_mm: BuildVolumeDims
    nozzle_size_mm: float | None = None
    extruder_count: int


class ExportOutput(BaseModel):
    path: str = Field(..., description="Absolute path the mesh was written to")
    format: str
    models: int = Field(..., description="Number of models written into the file")


# --- Tier 2: settings -----------------------------------------------------

class SettingOutput(BaseModel):
    """A setting's key + its resolved value (and type/unit when known)."""

    key: str
    value: Any = Field(default=None, description="Resolved value (float/int/bool/str)")
    type: str | None = None
    unit: str | None = None


class SupportsOutput(BaseModel):
    support_enable: bool
    support_type: str | None = Field(default=None, description="buildplate | everywhere")


# --- Tier 2: profiles -----------------------------------------------------

class MachineEntry(BaseModel):
    id: str
    name: str
    active: bool = False


class ListMachinesOutput(BaseModel):
    machines: list[MachineEntry]


class MaterialEntry(BaseModel):
    id: str
    name: str
    brand: str | None = None
    active: bool = False


class ListMaterialsOutput(BaseModel):
    materials: list[MaterialEntry]
    active: str | None = None


class ProfileSwitchOutput(BaseModel):
    id: str
    name: str
    active: bool


# --- Tier 2: export gcode -------------------------------------------------

class ExportGcodeOutput(BaseModel):
    path: str = Field(..., description="Absolute path the G-code was written to")
    lines: int = Field(..., description="Number of G-code lines written")
