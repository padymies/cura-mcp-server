"""set_infill_density tool: curated writer for infill_sparse_density (0-100%)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_infill_density(percent: float) -> SettingOutput:
        """Set the infill density as a percentage 0-100 (e.g. 20). Validated."""
        data = await client.call("set_infill_density", {"percent": percent})
        return SettingOutput(**data)
