"""set_quality tool: switch the active quality preset."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_quality(preset: str) -> SettingOutput:
        """Switch the quality preset (e.g. "draft", "normal", "fine"). Unknown or
        unavailable presets return an ``unknown_profile`` error listing valid ones.
        """
        data = await client.call("set_quality", {"preset": preset})
        return SettingOutput(**data)
