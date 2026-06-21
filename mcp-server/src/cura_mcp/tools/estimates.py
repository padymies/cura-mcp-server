"""get_estimates tool: read material and time from the last successful slice."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import EstimatesOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def get_estimates() -> EstimatesOutput:
        """Return material weight (g), length (m), cost, and print time.

        Requires a prior successful ``slice``. If no machine/material profile is
        active, ``profile_warning`` is set and the numbers may be unreliable.
        """
        data = await client.call("get_estimates")
        return EstimatesOutput(**data)
