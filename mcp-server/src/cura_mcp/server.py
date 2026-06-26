"""MCP server entrypoint.

Wires up a FastMCP server, constructs the plugin client, and registers every
tool module. Each tool module exposes ``register(mcp, client)``.
"""
from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from .client import PluginClient
from .config import load_settings
from .tools import (
    arrange_all,
    center_model,
    clear_plate,
    duplicate_model,
    estimates,
    export_gcode,
    export_model,
    get_all_user_settings,
    get_machine_info,
    get_model_settings,
    get_quality,
    get_setting,
    get_snapshot,
    group_models,
    list_machines,
    list_materials,
    list_models,
    list_quality_profiles,
    list_variants,
    load_model,
    merge_models,
    mirror_model,
    move_model,
    open_project,
    orientation,
    remove_model,
    reset_all_settings,
    reset_model_setting,
    reset_setting,
    rotate,
    save_project,
    scale_model,
    scale_to_fit,
    select_model,
    set_adhesion,
    set_infill_density,
    set_layer_height,
    set_mesh_type,
    set_model_setting,
    set_quality,
    set_setting,
    set_supports,
    status,
    switch_machine,
    switch_material,
    switch_variant,
    ungroup_model,
)
from .tools import slice as slice_tool


def build_server(mcp_factory: Callable[[str], FastMCP] = FastMCP) -> FastMCP:
    settings = load_settings()
    # ``mcp_factory`` defaults to a plain FastMCP. Local tooling can inject an
    # instrumented factory to wrap the central tool dispatch without this module
    # depending on anything outside the published package.
    mcp = mcp_factory("cura-mcp")
    client = PluginClient(settings)

    modules = (
        status,
        load_model,
        clear_plate,
        rotate,
        orientation,
        slice_tool,
        estimates,
        # Tier 1 — model management
        list_models,
        select_model,
        remove_model,
        duplicate_model,
        arrange_all,
        # Tier 1 — transforms
        scale_model,
        mirror_model,
        move_model,
        center_model,
        scale_to_fit,
        # Tier 1 — visibility / info / export
        get_machine_info,
        get_snapshot,
        export_model,
        # Tier 2 — settings
        get_setting,
        set_setting,
        reset_setting,
        # Tier 2 — curated writers
        set_layer_height,
        set_infill_density,
        set_supports,
        set_adhesion,
        set_quality,
        # Tier 2 — profiles
        list_machines,
        switch_machine,
        list_materials,
        switch_material,
        # Tier 2 — quality profile reads (set_quality already registered above)
        list_quality_profiles,
        get_quality,
        # Tier 2 — export gcode
        export_gcode,
        # Tier 3 (M1) — settings introspection + variants
        get_all_user_settings,
        reset_all_settings,
        list_variants,
        switch_variant,
        # Tier 3 (M2) — group / ungroup / merge
        group_models,
        ungroup_model,
        merge_models,
        # Tier 3 (M3) — project save / open
        save_project,
        open_project,
        # Tier 3 (M4) — per-object settings & mesh types
        set_model_setting,
        reset_model_setting,
        set_mesh_type,
        get_model_settings,
    )
    for module in modules:
        module.register(mcp, client, settings)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
