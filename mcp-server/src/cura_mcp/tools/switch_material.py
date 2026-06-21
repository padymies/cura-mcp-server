"""switch_material tool: set the active extruder's material."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ProfileSwitchOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def switch_material(name: str) -> ProfileSwitchOutput:
        """Set the active extruder's material by id or display name. ``unknown_profile``
        error if no compatible material matches (see list_materials).
        """
        data = await client.call("switch_material", {"name": name})
        return ProfileSwitchOutput(**data)
