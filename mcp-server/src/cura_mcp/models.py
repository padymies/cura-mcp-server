"""Pydantic models: the tool I/O surface and the plugin request/response contract.

These shapes are the versioned contract between the bridge and the plugin. The
plugin's ``router.py`` validates the same shapes on its side — keep them in sync.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    note: str | None = Field(
        default=None,
        description="Optional context, e.g. a custom quality profile layered on top.",
    )


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


# --- Tier 3 (M1): settings introspection / bulk reset ---------------------

class UserSetting(BaseModel):
    """One user override (something changed from the profile baseline)."""

    key: str
    value: Any = Field(default=None, description="The overridden value")
    type: str | None = None


class AllUserSettingsOutput(BaseModel):
    """Every user override, split by scope (global vs per-extruder)."""

    model_config = ConfigDict(populate_by_name=True)

    global_: list[UserSetting] = Field(
        default_factory=list, alias="global", description="Global (machine-wide) overrides"
    )
    extruders: list[list[UserSetting]] = Field(
        default_factory=list, description="Per-extruder overrides, one list per extruder"
    )


class ResetAllSettingsOutput(BaseModel):
    """Count of overrides removed when reverting to the profile baseline."""

    global_removed: int = Field(..., description="Global overrides removed")
    extruders_removed: list[int] = Field(
        default_factory=list, description="Overrides removed per extruder"
    )
    total_removed: int


# --- Tier 3 (M1): nozzle variants -----------------------------------------

class VariantEntry(BaseModel):
    id: str
    name: str
    active: bool = False


class ListVariantsOutput(BaseModel):
    variants: list[VariantEntry]
    active: str | None = Field(default=None, description="Active variant (nozzle) name")


class SwitchVariantOutput(BaseModel):
    id: str
    name: str
    active: bool
    material: str | None = Field(default=None, description="Resulting active material id")
    material_changed: bool = Field(
        default=False, description="True if the nozzle change swapped the active material"
    )
    note: str | None = Field(default=None, description="Human-readable material-compatibility note")


# --- v0.5: quality profile reads ------------------------------------------

class QualityProfileEntry(BaseModel):
    quality_type: str = Field(..., description="Stable key, e.g. 'standard' (use with set_quality)")
    name: str = Field(..., description="Display name, e.g. 'Standard'")
    active: bool = False


class QualityProfilesOutput(BaseModel):
    profiles: list[QualityProfileEntry]


# --- Tier 3 (M2): group / ungroup / merge ---------------------------------

class GroupOutput(BaseModel):
    """Result of a group/merge: the new group node id and its member ids."""

    node_id: str = Field(..., description="Id of the resulting group node")
    members: list[str] = Field(default_factory=list, description="Member model ids")


class UngroupOutput(BaseModel):
    """Result of an ungroup: the dissolved group id and its freed member ids."""

    node_id: str = Field(..., description="Id of the group that was dissolved")
    members: list[str] = Field(default_factory=list, description="Freed member model ids")


# --- Tier 3 (M3): project save / open -------------------------------------

class SaveProjectOutput(BaseModel):
    path: str = Field(..., description="Absolute path the project 3MF was written to")
    models: int = Field(..., description="Number of models saved into the project")


class OpenProjectOutput(BaseModel):
    """Preview or result of a (destructive) project open.

    With ``applied=False`` nothing changed — it is a dry-run PREVIEW (the default,
    when ``confirm`` was not set): ``machine``/``models`` are null and ``note``
    describes what *would* happen plus the warnings. With ``applied=True`` the
    workspace was actually opened.
    """

    applied: bool = Field(
        ..., description="False = preview only (nothing changed); True = workspace opened"
    )
    mode: str = Field(..., description="create_new | replace_active")
    destructive: bool = Field(
        ..., description="True when proceeding discards/overwrites workspace state with no undo"
    )
    previous_machine: str | None = Field(
        default=None, description="Active machine before opening (the current one)"
    )
    previous_models: int = Field(..., description="Model count before opening (the current plate)")
    machine: str | None = Field(
        default=None, description="Active machine after opening (null on a preview)"
    )
    models: int | None = Field(
        default=None, description="Model count after opening (null on a preview)"
    )
    note: str | None = Field(
        default=None, description="What happened, or on a preview what would happen + warnings"
    )


# --- Tier 3 (M4): per-object settings & mesh types ------------------------

class ModelSettingOutput(BaseModel):
    """Result of a per-object set/reset on one model."""

    node_id: str
    key: str
    value: Any = Field(default=None, description="Resolved per-object value")
    type: str | None = None
    removed: bool | None = Field(default=None, description="Set by reset_model_setting")


class MeshTypeOutput(BaseModel):
    node_id: str
    mesh_type: str = Field(
        ..., description="normal | support_mesh | anti_overhang_mesh | infill_mesh | cutting_mesh"
    )
    changed: bool = Field(default=False, description="False if it was already that type")


class ModelSettingEntry(BaseModel):
    key: str
    value: Any = None


class ModelSettingsOutput(BaseModel):
    """A model's per-object overrides + its current mesh type."""

    node_id: str
    mesh_type: str = Field(..., description="Current mesh role ('normal' if none)")
    settings: list[ModelSettingEntry] = Field(
        default_factory=list, description="Per-object overrides (excludes the mesh-type booleans)"
    )
