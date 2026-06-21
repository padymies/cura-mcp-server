"""Plugin lifecycle: start the local server when Cura is ready, stop on exit.

This is the one place that ties Cura's app lifecycle to our server. It also
initializes the main-thread dispatcher (must happen on the main thread).
"""
from __future__ import annotations

import threading

try:
    from UM.Extension import Extension
    from UM.Application import Application
    from UM.Logger import Logger
    from UM.Message import Message
except ImportError:  # pragma: no cover - allows import outside Cura for linting
    Extension = object  # type: ignore[assignment, misc]
    Application = None  # type: ignore[assignment]
    Logger = None  # type: ignore[assignment]
    Message = None  # type: ignore[assignment]

from .bridge.main_thread import init_main_thread_dispatcher
from .server.http_server import CuraMcpServer


def _log(msg: str) -> None:
    if Logger is not None:
        Logger.log("i", "[cura-mcp] %s", msg)


class CuraMcpPlugin(Extension):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self._server: CuraMcpServer | None = None
        self._thread: threading.Thread | None = None

        if Application is not None:
            # Adds an "Extensions > MCP Server > Show status" entry reporting
            # whether the local server is up and on which loopback port.
            self.setMenuName("MCP Server")
            self.addMenuItem("Show status", self._showStatus)

            app = Application.getInstance()
            # pluginsLoaded / applicationRunning fires once the main loop is up;
            # the dispatcher MUST be created on the main thread.
            app.callLater(self._start)  # type: ignore[attr-defined]
            app.applicationShuttingDown.connect(self._stop)  # type: ignore[attr-defined]

    def _start(self) -> None:
        try:
            init_main_thread_dispatcher()  # main thread
            self._server = CuraMcpServer()
            self._thread = threading.Thread(
                target=self._server.serve_forever, name="cura-mcp-http", daemon=True
            )
            self._thread.start()
            _log(f"server listening on {self._server.address}")
        except Exception as exc:  # noqa: BLE001
            _log(f"failed to start: {exc!r}")

    def _stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            _log("server stopped")

    def _showStatus(self) -> None:
        """Show MCP server connection status in a Cura notification."""
        if Message is None:
            return
        if self._server is not None:
            lines = [f"Connected \u2014 listening on {self._server.address}"]
            try:
                from .server.auth import default_token_file

                lines.append(f"Token file: {default_token_file()}")
            except Exception:  # noqa: BLE001
                pass
            text = "\n".join(lines)
        else:
            text = "Not running \u2014 the local server failed to start. Check the Cura log."
        Message(text, title="Cura MCP Server").show()
