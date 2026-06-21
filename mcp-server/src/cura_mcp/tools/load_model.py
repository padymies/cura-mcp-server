"""load_model tool: load a mesh file into the active Cura scene."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import LoadModelInput, LoadModelOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def load_model(path: str) -> LoadModelOutput:
        """Load a 3D model (.stl, .3mf, .obj) into Cura.

        The path is validated against the plugin's sandbox; paths outside the
        allow-list or with disallowed extensions are rejected.
        """
        LoadModelInput(path=path)  # client-side validation
        data = await client.call("load_model", {"path": path})
        return LoadModelOutput(**data)
