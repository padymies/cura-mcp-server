# Security Policy

## Threat model

The Cura plugin opens a local HTTP server inside Cura. That server is the entire
attack surface, and future versions may control hardware that heats and moves.
Controls:

- **Loopback-only binding** (`127.0.0.1`), never `0.0.0.0`.
- **Per-session token**: generated at plugin start, written to a user-readable
  local file, required on every request.
- **`Host` header allow-list** to blunt DNS-rebinding from a browser context.
- **Path sandbox** for file reads and writes: directory allow-list, traversal
  rejection, extension allow-list (read: `.stl`/`.3mf`/`.obj`; write: `.stl`/
  `.3mf`/`.gcode`/`.3mf` projects). The default allow-list is the user's home
  directory; override it with `CURA_MCP_ALLOWED_DIRS` (OS path-separated absolute
  paths — setting it *replaces* the default) to tighten or relocate the scope.
- **No printer control / no arbitrary G-code** in v1.
- **No outbound network, no telemetry** in either component.

## Supported versions

Security fixes target the latest release. See `CHANGELOG.md`.

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the repository's Security tab) rather than a public
issue. Include reproduction steps and affected versions. We aim to acknowledge
within a reasonable time and will coordinate disclosure.
