"""reset_all_settings tool: drop ALL user overrides, revert to profile baseline."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ResetAllSettingsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def reset_all_settings() -> ResetAllSettingsOutput:
        """Remove EVERY user override (global + all extruders), reverting the
        machine to its profile baseline, then re-slice. Returns the count removed
        per scope. Blast radius: this wipes all settings changes at once — it does
        not touch the scene or files. Undoable in Cura (Ctrl+Z) per removed key.
        """
        data = await client.call("reset_all_settings")
        return ResetAllSettingsOutput(**data)
