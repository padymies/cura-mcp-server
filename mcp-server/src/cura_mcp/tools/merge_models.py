"""merge_models tool: merge >=2 meshes into one object aligned at a shared origin."""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import PluginClient
from ..config import Settings
from ..models import GroupOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def merge_models(
        node_ids: Annotated[list[str], Field(min_length=2, description="Ids of >=2 models")],
    ) -> GroupOutput:
        """Merge two or more meshes into one object, aligning every part to the same
        origin (the dual-extrusion / multi-part alignment workflow). Returns the
        resulting group ``node_id`` + member ids. Unknown member id ->
        ``node_not_found``.
        """
        data = await client.call("merge_models", {"node_ids": list(node_ids)})
        return GroupOutput(**data)
