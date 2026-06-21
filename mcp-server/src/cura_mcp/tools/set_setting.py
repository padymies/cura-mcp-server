"""set_setting tool: guarded generic setting writer (power-user escape hatch)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_setting(key: str, value: bool | float | str) -> SettingOutput:
        """Set any GLOBAL Cura setting by key (the escape hatch behind the curated
        writers like set_layer_height). The value is validated against the
        setting's type, range, and options before it is applied, then re-read.

        Errors: ``unknown_setting`` (bad key), ``invalid_setting_value`` (wrong
        type / out of range / bad option), ``per_extruder_unsupported`` (the key is
        a per-extruder setting — not handled by v1).
        """
        data = await client.call("set_setting", {"key": key, "value": value})
        return SettingOutput(**data)
