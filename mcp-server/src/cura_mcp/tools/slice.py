"""slice tool: trigger a slice and wait for it to settle.

Uses the longer ``slice_timeout`` because slicing can take a while. The plugin
side performs the actual synchronous handshake (see cura-plugin/operations/slice.py);
here we just wait for its response.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import SliceOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def slice() -> SliceOutput:  # noqa: A001 - "slice" is the intended tool name
        """Slice the current scene and wait until slicing settles.

        Returns the terminal state: ``done`` (estimates are now valid), ``error``,
        or ``disabled`` (e.g. nothing to slice / model outside the build volume).
        """
        data = await client.call("slice", timeout=settings.slice_timeout)
        return SliceOutput(**data)
