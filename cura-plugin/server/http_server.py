"""Loopback-only HTTP server using only the Python standard library.

Single endpoint: ``POST /rpc`` with body ``{"method": str, "params": dict}``.
Every request is checked for a valid token and an allowed Host header before any
work happens. Bound to 127.0.0.1 exclusively.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import router
from .auth import TOKEN_HEADER, TokenManager, host_allowed

HOST = os.environ.get("CURA_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("CURA_MCP_PORT", "8765"))
_MAX_BODY = 8 * 1024 * 1024  # 8 MiB cap on request bodies


class _Handler(BaseHTTPRequestHandler):
    server_version = "CuraMcp/0.1"

    # Injected by CuraMcpServer.
    tokens: TokenManager

    def log_message(self, *args) -> None:  # noqa: ANN002 - silence default stderr logging
        pass

    def _reject(self, status: int, code: str, message: str) -> None:
        self._send(status, {"ok": False, "data": None, "error": {"code": code, "message": message}})

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - required name
        if self.path != "/rpc":
            self._reject(404, "cura_mcp_error", "Not found.")
            return
        if not host_allowed(self.headers.get("Host")):
            self._reject(403, "auth_error", "Host not allowed.")
            return
        if not self.tokens.check_token(self.headers.get(TOKEN_HEADER)):
            self._reject(401, "auth_error", "Invalid or missing token.")
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > _MAX_BODY:
            self._reject(400, "cura_mcp_error", "Invalid request body size.")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            method = payload["method"]
            params = payload.get("params", {})
        except (ValueError, KeyError, UnicodeDecodeError):
            self._reject(400, "cura_mcp_error", "Malformed request.")
            return

        envelope = router.dispatch(method, params)
        self._send(200, envelope)


class CuraMcpServer:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self._tokens = TokenManager()
        self._tokens.write()
        handler = type("_BoundHandler", (_Handler,), {"tokens": self._tokens})
        # ThreadingHTTPServer binds to the given address only — never 0.0.0.0.
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self.address = f"{host}:{port}"

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._tokens.cleanup()
