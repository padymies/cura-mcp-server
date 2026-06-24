"""get_all_user_settings tool: every user override, split by scope."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import AllUserSettingsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_all_user_settings() -> AllUserSettingsOutput:
        """List every setting the user (or a tool) has overridden from the active
        profile, split into ``global`` and per-``extruders`` scopes. This is the
        only way to see what was changed without probing keys one at a time.
        """
        data = await client.call("get_all_user_settings")
        return AllUserSettingsOutput(**data)
