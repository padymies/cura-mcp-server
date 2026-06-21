"""export_gcode tool: write the last slice's G-code to disk (sandboxed)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import ExportGcodeOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def export_gcode(path: str) -> ExportGcodeOutput:
        """Write the last successful slice's G-code to ``path`` (.gcode), inside the
        same sandbox as export_model. Requires a prior ``slice`` that reached DONE;
        otherwise returns an ``export_failed`` error (never an empty/stale file).
        """
        data = await client.call("export_gcode", {"path": path})
        return ExportGcodeOutput(**data)
