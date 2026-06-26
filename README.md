# cura-mcp-server

**Fully local. No hub. No telemetry.** An open-source [MCP](https://modelcontextprotocol.io)
server that lets an AI client (Claude Desktop, Claude Code, …) drive the
[UltiMaker Cura](https://ultimaker.com/software/ultimaker-cura/) slicer
conversationally: load a model, reorient it, slice it, and get material usage and
print time — without any third-party server in the loop.

> Ask: *"load this STL, rotate it 45° on X, slice it, and tell me how much
> filament it uses"* — and get a real answer from your own Cura install.

## How it works

Two components in one repo, talking over loopback only:

- **`mcp-server/`** — the bridge. Speaks MCP to your AI client and exposes typed
  tools. Runs in your own Python environment.
- **`cura-plugin/`** — a Cura plugin (standard-library only) that runs inside
  Cura, hosts a token-authenticated local server, and is the only thing that
  touches Cura's APIs.

See the component READMEs ([`mcp-server/`](mcp-server/README.md) and
[`cura-plugin/`](cura-plugin/README.md)) for details.

## Status

Early development. See `CHANGELOG.md`. Targets Cura **5.x** (validated minor
versions noted in `cura-plugin/plugin.json`).

## Install

Two pieces: the **plugin** (inside Cura) and the **bridge** (a small program your
MCP client launches). You do **not** need to install or manage Python yourself —
[`uv`](https://docs.astral.sh/uv/) runs the bridge and brings its own Python.

### 1. Install the Cura plugin

Download **`CuraMcp-<version>.zip`** from the
[latest release](https://github.com/padymies/cura-mcp-server/releases/latest) and
extract it into Cura's plugins folder. The zip already contains a correctly named
`CuraMcp/` folder, so there is nothing to rename:

- **Windows:** `%APPDATA%\cura\<version>\plugins\`
- **Linux:** `~/.local/share/cura/<version>/plugins/`
- **macOS:** `~/Library/Application Support/cura/<version>/plugins/`

You should end up with `…/plugins/CuraMcp/plugin.json`.

> **From source instead:** run `python scripts/package_plugin.py` and extract the
> generated `dist/CuraMcp-*.zip` (or copy [`cura-plugin/`](cura-plugin/) manually,
> renaming it to `CuraMcp` — the folder must be a valid Python package name).

Restart Cura. On startup the plugin writes a per-session token to
`~/.cura-mcp/token` and starts a loopback-only server on `127.0.0.1:8765`.
Check the binding with `netstat -an | findstr 8765` (Windows) or
`ss -ltn | grep 8765` (Linux) — the address must be `127.0.0.1`, not `0.0.0.0`.

### 2. Install uv

Install `uv` (a single binary, no system Python required) by following
[the official instructions](https://docs.astral.sh/uv/getting-started/installation/).
That's the only prerequisite for the bridge — there is no separate "install"
step; the client config below runs it on demand.

### 3. Point your MCP client at the bridge

**Claude Desktop / Claude Code** — see
[`examples/claude-desktop-config.json`](examples/claude-desktop-config.json):

```json
{
  "mcpServers": {
    "cura": {
      "command": "uvx",
      "args": ["cura-mcp"],
      "env": { "CURA_MCP_PORT": "8765" }
    }
  }
}
```

**Codex** — see [`examples/codex-config.toml`](examples/codex-config.toml); add to
`~/.codex/config.toml`:

```toml
[mcp_servers.cura]
command = "uvx"
args = ["cura-mcp"]
startup_timeout_sec = 30

[mcp_servers.cura.env]
CURA_MCP_PORT = "8765"
```

`uvx cura-mcp` downloads (and caches) the published package and runs it. To track
the latest `main` instead of a release, point `uvx` at the repo:

```json
{ "command": "uvx",
  "args": ["--from",
           "git+https://github.com/padymies/cura-mcp-server.git#subdirectory=mcp-server",
           "cura-mcp"] }
```

Restart the client. With Cura open, ask it to `get_status` first to confirm the
connection.

> **From source (development):** `cd mcp-server && pip install -e ".[dev]"`, then
> use `"command": "python", "args": ["-m", "cura_mcp.server"]`.

### Configuration (environment variables)

| Variable | Default | Used by |
|----------|---------|---------|
| `CURA_MCP_HOST` | `127.0.0.1` | both |
| `CURA_MCP_PORT` | `8765` | both |
| `CURA_MCP_TOKEN_FILE` | `~/.cura-mcp/token` | both (must match) |
| `CURA_MCP_TIMEOUT` | `30` | bridge |
| `CURA_MCP_SLICE_TIMEOUT` | `300` | bridge |
| `CURA_MCP_ALLOWED_DIRS` | user home dir | plugin (filesystem sandbox) |

#### Restricting file access to specific folders

By default the plugin may read/write models anywhere under your home directory.
To limit it to specific folders, set `CURA_MCP_ALLOWED_DIRS` to an
**OS-path-separated** list of absolute paths (`;` on Windows, `:` on Linux/macOS).
Setting it **replaces** the default — only the listed folders are allowed.

This variable is read by the **plugin**, so it must be set in **Cura's own
environment** (the MCP client `env` only reaches the bridge, which doesn't use
it). Set it before launching Cura, e.g.:

```bat
:: Windows — or set it as a user env var (System Properties → Environment Variables)
set "CURA_MCP_ALLOWED_DIRS=C:\Users\me\3D Models;C:\Users\me\Downloads"
"C:\Program Files\UltiMaker Cura 5.x\Cura.exe"
```

```bash
# Linux / macOS
CURA_MCP_ALLOWED_DIRS="$HOME/3D Models:$HOME/Downloads" cura
```

## Try this

Drop [`agent/cura-slicing-assistant.md`](agent/cura-slicing-assistant.md) into
your MCP client as a system prompt — it maps your intent to the right tools, so
you don't need to know any tool names — then ask:

- *"Load `~/models/bracket.stl`, lay it flat, set 0.2 mm layers and 20 % infill,
  slice it, and tell me filament and print time — then show me the plate."*
- *"I want 6 of these on one plate. Duplicate, arrange them, slice, and tell me
  total filament and how many fit."*
- *"Try this at 0.12 mm and again at 0.28 mm and compare time vs material."*
- *"Rotate it 45° on X, re-slice, and tell me how the totals changed."*

## Security

This software opens a local server and (in future versions) can interact with
hardware. Read [`SECURITY.md`](SECURITY.md). The server binds to `127.0.0.1`
only, requires a per-session token, and makes no outbound network calls. File
reads/writes are sandboxed to your home directory by default; set
`CURA_MCP_ALLOWED_DIRS` (OS path-separated) to restrict or relocate that scope.

## License & disclaimers

MIT — see [`LICENSE`](LICENSE).

Not affiliated with, endorsed by, or sponsored by UltiMaker. "Cura" and
"UltiMaker" are trademarks of UltiMaker B.V., used here only to identify
compatibility.

This software interacts with 3D printing software and may, in future versions,
control hardware that reaches high temperatures and moves mechanically. **Use at
your own risk.** The authors accept no liability for damage to equipment,
material, or property.
