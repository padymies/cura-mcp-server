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
