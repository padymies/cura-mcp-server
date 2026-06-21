"""list_materials tool: materials compatible with the active machine + nozzle."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ListMaterialsOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_materials() -> ListMaterialsOutput:
        """List materials available for the active machine + nozzle, marking the
        active one (and returning its id in ``active``).
        """
        data = await client.call("list_materials")
        return ListMaterialsOutput(**data)
