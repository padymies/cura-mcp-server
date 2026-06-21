"""set_adhesion tool: set the build-plate adhesion type."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_adhesion(type: str) -> SettingOutput:  # noqa: A002
        """Set build-plate adhesion: "skirt", "brim", "raft", or "none"."""
        data = await client.call("set_adhesion", {"type": type})
        return SettingOutput(**data)
