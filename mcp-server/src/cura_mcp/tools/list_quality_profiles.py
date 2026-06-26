"""list_quality_profiles tool: quality presets available for the active machine."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import QualityProfilesOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_quality_profiles() -> QualityProfilesOutput:
        """List the quality presets available for the active machine (``quality_type``
        + display name), marking the active one. Machines differ (e.g. the Ender 3 S1
        offers low/standard/super/adaptive). Apply one with ``set_quality``.
        """
        data = await client.call("list_quality_profiles")
        return QualityProfilesOutput(**data)
