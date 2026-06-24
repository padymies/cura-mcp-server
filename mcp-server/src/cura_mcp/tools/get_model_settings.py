"""get_model_settings tool: a model's per-object overrides + its mesh type."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ModelSettingsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_model_settings(node_id: str) -> ModelSettingsOutput:
        """List a model's per-object setting overrides and its current mesh type
        (``normal`` if none). Unknown model → ``node_not_found``.
        """
        data = await client.call("get_model_settings", {"node_id": node_id})
        return ModelSettingsOutput(**data)
