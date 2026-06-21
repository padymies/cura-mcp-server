"""center_model tool: center a model on the plate."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import TransformOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def center_model(node_id: str) -> TransformOutput:
        """Center the model with ``node_id`` on the build plate and drop it to the
        plate surface.
        """
        data = await client.call("center_model", {"node_id": node_id})
        return TransformOutput(**data)
