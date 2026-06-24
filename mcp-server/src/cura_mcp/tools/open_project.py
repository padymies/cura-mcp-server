"""open_project tool: replace the workspace with a Cura project 3MF."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import PluginClient
from ..config import Settings
from ..models import OpenProjectOutput


def register(mcp: FastMCP, client: PluginClient, settings: Settings) -> None:
    @mcp.tool()
    async def open_project(
        path: str, confirm: bool = False, mode: str = "create_new"
    ) -> OpenProjectOutput:
        """Open a Cura project ``.3mf``. DESTRUCTIVE and not undoable.

        Two-step BY DESIGN: call once with ``confirm=False`` (the default) to get a
        PREVIEW (``applied=False``) that says exactly what will happen and what the
        current workspace is — show it to the user, and only call again with
        ``confirm=True`` once they agree.

        ``mode``:
          - ``create_new`` (default): load the project's scene + settings into a
            NEW printer instance; the current printer stays in the list. Never
            overwrites an existing printer's profile.
          - ``replace_active``: OVERWRITE the active printer's profile/material/
            settings with the project's, in place (only valid when the project was
            made for the same printer definition). No undo — run save_project first
            if unsure. (May be gated off in this build; the preview will say so.)

        Path must be a ``.3mf`` inside the allowed directories (``invalid_path``
        otherwise); a failed load -> ``load_failed``.
        """
        data = await client.call(
            "open_project", {"path": path, "confirm": confirm, "mode": mode}
        )
        return OpenProjectOutput(**data)
