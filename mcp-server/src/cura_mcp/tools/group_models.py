"""group_models tool: group >=2 models so they move as one."""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..client import PluginClient
from ..config import Settings
from ..models import GroupOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def group_models(
        node_ids: Annotated[list[str], Field(min_length=2, description="Ids of >=2 models")],
    ) -> GroupOutput:
        """Group two or more models into one group node so they move together in
        Cura. Returns the new group's ``node_id`` plus its member ids; pass that
        ``node_id`` to ``ungroup_model`` later. Members still appear individually in
        ``list_models``; MCP transforms target individual members, not the group.
        Unknown member id -> ``node_not_found``.
        """
        data = await client.call("group_models", {"node_ids": list(node_ids)})
        return GroupOutput(**data)
