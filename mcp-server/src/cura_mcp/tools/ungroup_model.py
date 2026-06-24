"""ungroup_model tool: dissolve a group back into its members."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import UngroupOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def ungroup_model(node_id: str) -> UngroupOutput:
        """Ungroup a group node (the id returned by ``group_models``/``merge_models``)
        back into its individual members. Returns the freed member ids. If
        ``node_id`` is not a group, returns ``node_not_found``.
        """
        data = await client.call("ungroup_model", {"node_id": node_id})
        return UngroupOutput(**data)
