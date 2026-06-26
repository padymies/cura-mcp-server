# cura-mcp (bridge)

The MCP server. Speaks MCP to your AI client and forwards each tool call to the
Cura plugin over loopback HTTP. Knows nothing about Cura internals — it is pure
transport, schemas, and error mapping.

## Run (users)

Users don't install this directly — their MCP client launches it via
[`uv`](https://docs.astral.sh/uv/): `uvx cura-mcp` (see the top-level
[`README`](../README.md#install)). `uv` brings its own Python, so no separate
Python install is required.

## Install (dev)

```bash
cd mcp-server
pip install -e ".[dev]"
python -m cura_mcp.server
```

Requires Cura running with the `cura-plugin` installed (the bridge fails fast
with a clear error otherwise). Configuration via env vars — see `config.py`:

- `CURA_MCP_HOST` (default `127.0.0.1`)
- `CURA_MCP_PORT` (default `8765`)
- `CURA_MCP_TOKEN_FILE` (default: platform user dir `~/.cura-mcp/token`)
- `CURA_MCP_TIMEOUT` (default `30` seconds; slice waits use a longer timeout)

## Layout

```
src/cura_mcp/
  server.py     MCP entrypoint; registers tools
  client.py     HTTP client to the plugin (token-authenticated)
  models.py     pydantic schemas (tool I/O + plugin contract)
  config.py     settings
  errors.py     typed error hierarchy
  tools/        one module per tool
```
