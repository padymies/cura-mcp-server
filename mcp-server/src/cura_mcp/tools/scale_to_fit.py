"""scale_to_fit tool: shrink a model to fit the build volume."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import TransformOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def scale_to_fit(node_id: str) -> TransformOutput:
        """Uniformly scale the model with ``node_id`` DOWN so it fits the build
        volume (with a small margin). No-op if it already fits; then re-centered.
        """
        data = await client.call("scale_to_fit", {"node_id": node_id})
        return TransformOutput(**data)
