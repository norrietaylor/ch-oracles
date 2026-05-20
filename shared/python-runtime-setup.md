## Python runtime setup

For workflows that operate on a Python repo, provision the toolchain before
the agent step begins. ch-oracles standardizes on `uv` for environment and
dependency management.

### Install uv and the project's interpreter

```yaml
- uses: astral-sh/setup-uv@v3
  with:
    enable-cache: true

- name: Install Python interpreter
  run: uv python install
```

If `pyproject.toml` declares a `requires-python` constraint, `uv python
install` honors it. Otherwise the latest stable cpython is installed.

### Project sync

```yaml
- name: Sync project
  run: uv sync --frozen
```

`--frozen` fails the run if `uv.lock` is missing or stale, which surfaces
dep drift as a chore signal rather than a silent recompute.

### Network egress

This workflow's lock file MUST declare:

```yaml
network:
  allowed: [defaults, python]
```

The `python` ecosystem id covers `pypi.org` and `files.pythonhosted.org`.
`defaults` covers GitHub API endpoints.

### Tool checks

```bash
command -v uv >/dev/null 2>&1 || { echo "uv not found" >&2; exit 1; }
uv --version
uv run python --version
```

### Optional: ruff, mypy, pytest, pip-audit

These are dev dependencies declared in `pyproject.toml` and installed via
`uv sync`. Lint and worker chores invoke them via `uv run`:

```bash
uv run ruff format --check
uv run ruff check
uv run mypy
uv run pytest
uv run pip-audit  # dep-bump chore only
```
