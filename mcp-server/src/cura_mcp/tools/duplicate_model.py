"""duplicate_model tool: copy a model N times."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import DuplicateModelOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def duplicate_model(node_id: str, count: int = 1) -> DuplicateModelOutput:
        """Duplicate the model with ``node_id`` ``count`` times.

        Copies are auto-arranged into free spots on the plate (existing models stay
        put) and get distinct node_ids. Returns a ``node_not_found`` error for an
        unknown id.
        """
        data = await client.call("duplicate_model", {"node_id": node_id, "count": count})
        return DuplicateModelOutput(**data)
