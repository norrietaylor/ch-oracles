## Python build commands

Default verification commands for Python projects. Workers and lint chores
invoke these unless `AGENTS.md` overrides them.

### Verification gate

Every command exits 0 before a PR opens:

```bash
uv sync --frozen
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
```

`--frozen` ensures the lockfile matches the manifest. Drop it only when the
PR's purpose is to update the lockfile (e.g., `trivial-dep-bump-python`).

### Lint commands

`mode: report`:

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
```

`mode: autofix`:

```bash
uv run ruff format
uv run ruff check --fix
# mypy has no --fix mode; type errors stay reported, never auto-applied.
```

### Dep-bump commands

```bash
uv lock --upgrade
uv sync --frozen
uv run pip-audit --strict  # reject if any vulnerability remains
```

A patch-level bump is rejected if:

- `pyproject.toml` was mutated (only `uv.lock` may change).
- `pip-audit --strict` reports any vulnerability of severity `high` or
  `critical` after the upgrade.
- The Python interpreter version constraint changed.
