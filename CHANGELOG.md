# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold: bridge (`mcp-server/`) and Cura plugin
  (`cura-plugin/`).
- Main-thread marshalling helper and synchronous slice handshake skeleton.
- Tool surface: `get_status`, `load_model`, `rotate`, `lay_flat`,
  `reset_orientation`, `slice`, `get_estimates`.
- Security baseline: loopback-only binding, per-session token, `Host` check,
  path sandbox.

[Unreleased]: https://github.com/padicodeai-cloud/cura-mcp-server
