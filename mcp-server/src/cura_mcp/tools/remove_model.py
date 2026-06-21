"""remove_model tool: remove a single model from the plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import RemoveModelOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def remove_model(node_id: str) -> RemoveModelOutput:
        """Remove the model with ``node_id`` from the build plate (undoable in Cura).

        Returns a ``node_not_found`` error if no model has that id. To clear the
        whole plate at once, use clear_plate instead.
        """
        data = await client.call("remove_model", {"node_id": node_id})
        return RemoveModelOutput(**data)
