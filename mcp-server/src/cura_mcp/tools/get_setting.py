"""get_setting tool: read a resolved Cura setting value."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_setting(key: str) -> SettingOutput:
        """Read the current resolved value of a Cura setting (e.g. ``layer_height``,
        ``infill_sparse_density``). Returns an ``unknown_setting`` error if the key
        does not exist in the active machine definition.
        """
        data = await client.call("get_setting", {"key": key})
        return SettingOutput(**data)
