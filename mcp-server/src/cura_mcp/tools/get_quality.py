"""get_quality tool: read the active quality preset."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_quality() -> SettingOutput:
        """Return the active quality preset as a ``quality`` setting — its
        ``quality_type`` (e.g. "standard"). If a custom profile is layered on top,
        ``note`` describes it. Use ``list_quality_profiles`` to see the options.
        """
        data = await client.call("get_quality")
        return SettingOutput(**data)
