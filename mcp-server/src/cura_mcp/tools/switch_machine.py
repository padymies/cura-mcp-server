"""switch_machine tool: activate a configured printer."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ProfileSwitchOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def switch_machine(name: str) -> ProfileSwitchOutput:
        """Activate a configured printer by id or display name. ``unknown_profile``
        error if there's no such machine (see list_machines).
        """
        data = await client.call("switch_machine", {"name": name})
        return ProfileSwitchOutput(**data)
