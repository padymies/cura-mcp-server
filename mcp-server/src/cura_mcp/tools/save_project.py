"""save_project tool: write the whole workspace to a Cura project 3MF."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SaveProjectOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def save_project(path: str) -> SaveProjectOutput:
        """Save the ENTIRE workspace — scene models, active machine, material +
        nozzle, and every user setting — to a Cura project ``.3mf`` (reopenable with
        ``open_project``). This is NOT ``export_model`` (which writes mesh geometry
        only). Path must be a ``.3mf`` inside the allowed directories; otherwise
        ``invalid_path``. Writer failure -> ``export_failed``.
        """
        data = await client.call("save_project", {"path": path})
        return SaveProjectOutput(**data)
