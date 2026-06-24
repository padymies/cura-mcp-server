"""set_mesh_type tool: set a model's mesh role (support blocker, modifier, etc.)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import MeshTypeOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def set_mesh_type(node_id: str, type: str) -> MeshTypeOutput:  # noqa: A002
        """Set a model's mesh role. ``type`` ∈ {``normal``, ``support_mesh``,
        ``anti_overhang_mesh``, ``infill_mesh``, ``cutting_mesh``}; ``normal`` clears
        the role. ``anti_overhang_mesh`` = support blocker, ``support_mesh`` =
        print-as-support, ``infill_mesh``/``cutting_mesh`` = modifier mesh. NOTE: a
        modifier/cutting/support/blocker mesh only does anything where it OVERLAPS
        the base model — this sets the role, it does not position the mesh. Invalid
        type → ``invalid_setting_value``; unknown model → ``node_not_found``.
        """
        data = await client.call("set_mesh_type", {"node_id": node_id, "type": type})
        return MeshTypeOutput(**data)
