# Contributing

Thanks for considering a contribution.

## Ground rules

- This project is **clean-room**. Do **not** paste source from UltiMaker Cura,
  Uranium, or any proprietary plugin (including AuraFriday's `cura_mcp`). Read
  public APIs and write original code.
- Keep the **plugin dependency-free** (Python standard library only) — it runs
  inside Cura's bundled interpreter. The bridge may use normal dependencies.
- All Cura-internal API access stays inside `cura-plugin/adapters/cura_api.py`.

## Developer Certificate of Origin (DCO)

We use the [DCO](https://developercertificate.org/) instead of a CLA. Sign off
every commit:

```
git commit -s -m "your message"
```

This adds a `Signed-off-by: Your Name <email>` line certifying you wrote the
code or have the right to submit it under the MIT license.

## Workflow

1. Open an issue describing the change before large PRs.
2. Branch, implement, and keep the change focused.
3. Run `ruff`, `mypy`, and `pytest` locally (CI runs them too).
4. Update `CHANGELOG.md` when behavior changes.
5. Open a PR using the template.

## Code style

- Python, typed, `ruff`-formatted. Public tool I/O is validated.
- Small modules, one responsibility each. Match the structure described in the
  component READMEs ([`mcp-server/`](mcp-server/README.md),
  [`cura-plugin/`](cura-plugin/README.md)).

## Releasing (maintainers)

The bridge is published to PyPI as `cura-mcp` so users can run it with
`uvx cura-mcp`. Publishing uses **PyPI Trusted Publishing** (OIDC) — no API token
is stored in the repo.

One-time setup on PyPI (Account → Publishing): add a *pending* trusted publisher
for project `cura-mcp`, owner `padymies`, repo `cura-mcp-server`, workflow
`release.yml`, environment `pypi`.

To cut a release:

1. Bump the version in `mcp-server/pyproject.toml` (and `cura-plugin/plugin.json`
   if the plugin changed) and update `CHANGELOG.md`.
2. Tag and push: `git tag vX.Y.Z && git push --tags`.
3. Publish a GitHub Release for that tag. The `Release (PyPI)` workflow then
   builds and uploads the wheel/sdist. Nothing publishes on a normal push.
