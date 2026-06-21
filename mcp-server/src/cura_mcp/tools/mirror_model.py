"""mirror_model tool: mirror a model about an axis."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import Axis, TransformOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def mirror_model(node_id: str, axis: Axis) -> TransformOutput:
        """Mirror the model with ``node_id`` about ``axis`` (x, y, or z), around its
        own centre.
        """
        data = await client.call("mirror_model", {"node_id": node_id, "axis": axis})
        return TransformOutput(**data)
