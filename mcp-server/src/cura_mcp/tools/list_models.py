"""list_models tool: enumerate every model on the build plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ListModelsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_models() -> ListModelsOutput:
        """List every printable model on the build plate (node_id, bounds, position).

        Use the returned ``node_id`` to target a specific model with select/remove/
        duplicate/transform tools.
        """
        data = await client.call("list_models")
        return ListModelsOutput(**data)
