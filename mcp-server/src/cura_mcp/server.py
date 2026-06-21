"""MCP server entrypoint.

Wires up a FastMCP server, constructs the plugin client, and registers every
tool module. Each tool module exposes ``register(mcp, client)``.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import PluginClient
from .config import load_settings
from .tools import (
    arrange_all,
    center_model,
    clear_plate,
    duplicate_model,
    estimates,
    export_model,
    get_machine_info,
    get_snapshot,
    list_models,
    load_model,
    mirror_model,
    move_model,
    orientation,
    remove_model,
    rotate,
    scale_model,
    scale_to_fit,
    select_model,
    status,
)
from .tools import slice as slice_tool


def build_server() -> FastMCP:
    settings = load_settings()
    mcp = FastMCP("cura-mcp")
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
    )
    for module in modules:
        module.register(mcp, client, settings)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
