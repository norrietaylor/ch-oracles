# Python

## Wrappers installed for a Python consumer

- `chore-style-python.yml` — `ruff format` + `ruff check` + `mypy`; mode:
  report | autofix.
- `trivial-dep-bump-python.yml` — patch-level `uv.lock` updates with
  auto-merge.
- Universal wrappers.

## Toolchain provisioning

ch-oracles standardizes on `uv` for environment and dependency management:

```yaml
- uses: astral-sh/setup-uv@v3
  with:
    enable-cache: true
- run: uv python install
- run: uv sync --frozen
```

If `pyproject.toml` declares a `requires-python` constraint, `uv python
install` honors it.

## Verification commands

Defaults (from `shared/python-build-commands.md`):

```bash
uv sync --frozen
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

Override via `## Build Commands (ch-oracles override)` in
`.github/AGENTS.md`.

## Network egress

The Python chore's lock file declares
`network.allowed: [defaults, python]`, unioning in `pypi.org` and
`files.pythonhosted.org`.

## Why uv (and not pip/poetry/hatch)

uv is significantly faster, has lockfile-first semantics, and is the
fastest-moving Python toolchain in 2026. A future ADR may revisit if the
ecosystem consolidates around a different default; for now `uv` is the
single declared substrate.

A repo using a different toolchain can override every command via
`AGENTS.md`, but the runtime setup (uv install + uv sync) still runs
because the lock file's `bash:` allowlist gates which commands the agent
can invoke. To swap toolchains fully, the consumer would need to fork the
runtime-setup fragment — a future ADR will track this if demand emerges.

## Limitations

- The chore rejects any `pyproject.toml` mutation in patch-level bump
  mode; only `uv.lock` may change.
- `pip-audit --strict` runs as the security gate; the chore rejects on
  any high/critical finding in the post-upgrade state.
- mypy findings in `mode: autofix` block the PR (mypy has no `--fix`).
