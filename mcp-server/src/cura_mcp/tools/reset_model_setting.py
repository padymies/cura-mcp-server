"""reset_model_setting tool: remove one per-object override from a model."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ModelSettingOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def reset_model_setting(node_id: str, key: str) -> ModelSettingOutput:
        """Remove a single per-object override from a model (``removed`` is False if
        it wasn't set). Unknown key → ``unknown_setting``; unknown model →
        ``node_not_found``.
        """
        data = await client.call("reset_model_setting", {"node_id": node_id, "key": key})
        return ModelSettingOutput(**data)
