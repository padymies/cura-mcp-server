"""Bridge tests that run without Cura. Schema validation + error mapping."""
from __future__ import annotations

import pytest

from cura_mcp.errors import (
    CuraMcpError,
    CuraNotRunning,
    InvalidSettingValue,
    NodeNotFound,
    PerExtruderUnsupported,
    SliceFailed,
    UnknownProfile,
    UnknownSetting,
    from_plugin_code,
)
from cura_mcp.models import (
    ArrangeAllOutput,
    BuildVolumeDims,
    ClearPlateOutput,
    DuplicateModelOutput,
    EstimatesOutput,
    ExportGcodeOutput,
    ExportOutput,
    ExtruderEstimate,
    ListMachinesOutput,
    ListMaterialsOutput,
    ListModelsOutput,
    LoadModelInput,
    MachineEntry,
    MachineInfoOutput,
    MaterialEntry,
    ModelInfo,
    PluginResponse,
    ProfileSwitchOutput,
    RotateInput,
    SettingOutput,
    SupportsOutput,
    TransformOutput,
)
from cura_mcp.server import build_server


def test_error_code_roundtrip() -> None:
    err = from_plugin_code("slice_failed", "outside build volume")
    assert isinstance(err, SliceFailed)
    assert err.code == "slice_failed"


def test_unknown_code_falls_back_to_base() -> None:
    err = from_plugin_code("something_new", "msg")
    assert type(err) is CuraMcpError


def test_rotate_input_validation() -> None:
    ok = RotateInput(axis="x", degrees=45)
    assert ok.degrees == 45
    with pytest.raises(ValueError):
        RotateInput(axis="w", degrees=10)  # invalid axis


def test_load_input_requires_path() -> None:
    with pytest.raises(ValueError):
        LoadModelInput()  # type: ignore[call-arg]


def test_plugin_response_envelope() -> None:
    ok = PluginResponse.model_validate({"ok": True, "data": {"x": 1}})
    assert ok.ok and ok.data == {"x": 1}
    bad = PluginResponse.model_validate(
        {"ok": False, "error": {"code": "auth_error", "message": "no token"}}
    )
    assert not bad.ok and bad.error is not None
    assert bad.error.code == "auth_error"


def test_estimates_output_shape() -> None:
    out = EstimatesOutput(
        extruders=[ExtruderEstimate(weight_g=32.0, length_m=4.1)],
        total_weight_g=32.0,
        total_length_m=4.1,
        print_time_seconds=6420,
    )
    assert out.total_weight_g == 32.0


def test_cura_not_running_is_cura_mcp_error() -> None:
    assert issubclass(CuraNotRunning, CuraMcpError)


def test_clear_plate_output_shape() -> None:
    out = ClearPlateOutput(cleared=2)
    assert out.cleared == 2
    with pytest.raises(ValueError):
        ClearPlateOutput()  # type: ignore[call-arg]  # cleared is required


def test_node_not_found_roundtrip() -> None:
    err = from_plugin_code("node_not_found", "no model with id 'x'")
    assert isinstance(err, NodeNotFound)
    assert err.code == "node_not_found"


def test_list_models_output_shape() -> None:
    info = ModelInfo(node_id="Cubo", bounds_mm=[40.0, 40.0, 40.0], position_mm=[0.0, 20.0, 0.0])
    out = ListModelsOutput(models=[info])
    assert out.models[0].node_id == "Cubo"
    assert out.models[0].position_mm == [0.0, 20.0, 0.0]


def test_duplicate_and_arrange_output_shapes() -> None:
    dup = DuplicateModelOutput(original="Cubo", created=["Cubo (1)", "Cubo (2)"], count=2)
    assert dup.count == 2 and len(dup.created) == 2
    assert ArrangeAllOutput(arranged=3).arranged == 3


def test_transform_output_shape() -> None:
    out = TransformOutput(
        node_id="Cubo", bounds_mm=[80.0, 80.0, 80.0], position_mm=[0.0, 40.0, 0.0]
    )
    assert out.fits_build_volume is True  # default
    assert out.bounds_mm == [80.0, 80.0, 80.0]


def test_machine_info_and_export_shapes() -> None:
    info = MachineInfoOutput(
        machine_name="ENDER 3 S1",
        build_volume_mm=BuildVolumeDims(width=220.0, depth=220.0, height=270.0),
        nozzle_size_mm=0.4,
        extruder_count=1,
    )
    assert info.build_volume_mm.height == 270.0
    out = ExportOutput(path="C:/Users/x/out.stl", format="stl", models=2)
    assert out.models == 2


def test_setting_output_shape() -> None:
    out = SettingOutput(key="layer_height", value=0.2, type="float", unit="mm")
    assert out.value == 0.2 and out.unit == "mm"
    # value is polymorphic
    assert SettingOutput(key="adhesion_type", value="brim", type="enum").value == "brim"
    assert SettingOutput(key="support_enable", value=True, type="bool").value is True


def test_tier2_error_roundtrips() -> None:
    assert isinstance(from_plugin_code("unknown_setting", "x"), UnknownSetting)
    assert isinstance(from_plugin_code("invalid_setting_value", "x"), InvalidSettingValue)
    assert isinstance(from_plugin_code("per_extruder_unsupported", "x"), PerExtruderUnsupported)
    assert isinstance(from_plugin_code("unknown_profile", "x"), UnknownProfile)


def test_tier2_profile_and_export_shapes() -> None:
    machines = ListMachinesOutput(
        machines=[MachineEntry(id="ender3", name="Ender 3 S1", active=True)]
    )
    assert machines.machines[0].active is True
    mats = ListMaterialsOutput(
        materials=[MaterialEntry(id="generic_pla", name="PLA", brand="Generic", active=True)],
        active="generic_pla",
    )
    assert mats.active == "generic_pla"
    assert ProfileSwitchOutput(id="generic_pla", name="PLA", active=True).active is True
    assert SupportsOutput(support_enable=True, support_type="everywhere").support_type
    assert ExportGcodeOutput(path="C:/Users/x/out.gcode", lines=1234).lines == 1234


async def test_server_registers_tier1_and_tier2_tools() -> None:
    mcp = build_server()
    names = {tool.name for tool in await mcp.list_tools()}
    assert {
        "list_models",
        "select_model",
        "remove_model",
        "duplicate_model",
        "arrange_all",
        "scale_model",
        "mirror_model",
        "move_model",
        "center_model",
        "scale_to_fit",
        "get_machine_info",
        "get_snapshot",
        "export_model",
        "get_setting",
        "set_setting",
        "reset_setting",
        "set_layer_height",
        "set_infill_density",
        "set_supports",
        "set_adhesion",
        "set_quality",
        "list_machines",
        "switch_machine",
        "list_materials",
        "switch_material",
        "export_gcode",
    } <= names
