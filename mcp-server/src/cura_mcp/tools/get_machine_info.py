"""get_machine_info tool: active machine + build volume + nozzle."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import MachineInfoOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_machine_info() -> MachineInfoOutput:
        """Return the active machine name, build volume (width/depth/height mm),
        nozzle size, and extruder count.
        """
        data = await client.call("get_machine_info")
        return MachineInfoOutput(**data)
