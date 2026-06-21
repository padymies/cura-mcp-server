"""export_model tool: write model(s) to disk (sandboxed output path)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ExportOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def export_model(path: str, target: str = "all", format: str = "stl") -> ExportOutput:
        """Write model(s) to an STL or 3MF file on disk.

        ``target`` is "all" (the whole plate) or a specific ``node_id``. The output
        ``path`` must pass the same sandbox as load_model (inside an allowed dir, no
        traversal, .stl/.3mf only); the file extension determines the format. An
        out-of-sandbox path returns an ``invalid_path`` error.
        """
        data = await client.call(
            "export_model", {"target": target, "path": path, "format": format}
        )
        return ExportOutput(**data)
