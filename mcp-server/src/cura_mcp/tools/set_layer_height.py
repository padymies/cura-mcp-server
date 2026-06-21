"""set_layer_height tool: curated writer for layer_height."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_layer_height(mm: float) -> SettingOutput:
        """Set the layer height in millimetres (e.g. 0.2). Validated and re-read."""
        data = await client.call("set_layer_height", {"mm": mm})
        return SettingOutput(**data)
