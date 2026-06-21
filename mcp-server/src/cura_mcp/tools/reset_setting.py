"""reset_setting tool: drop a user override, reverting to the profile value."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def reset_setting(key: str) -> SettingOutput:
        """Remove a user override for ``key``, reverting it to the active profile's
        value (returns the reverted value). ``unknown_setting`` error for a bad key.
        """
        data = await client.call("reset_setting", {"key": key})
        return SettingOutput(**data)
