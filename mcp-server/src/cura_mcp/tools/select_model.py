"""select_model tool: make a model the active selection."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SelectModelOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def select_model(node_id: str) -> SelectModelOutput:
        """Make the model with ``node_id`` the active selection in Cura.

        Returns a ``node_not_found`` error if no model has that id (see list_models).
        """
        data = await client.call("select_model", {"node_id": node_id})
        return SelectModelOutput(**data)
