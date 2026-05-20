## Nickel build commands

Default lint commands for Nickel files. As with TOML, there is no separate
"build" or "test" surface in ch-oracles' scope — these reduce to lint and
typecheck.

### Verification gate

```bash
nickel format --check **/*.ncl
nickel typecheck **/*.ncl
```

Both commands must exit 0. `**/*.ncl` is expanded by the shell (globstar).
For shells without globstar, fall back to `find . -name '*.ncl' -print0 |
xargs -0 nickel typecheck`.

### Lint commands

`mode: report`:

```bash
nickel format --check **/*.ncl
nickel typecheck **/*.ncl
```

`mode: autofix`:

```bash
nickel format **/*.ncl  # rewrites files in place
nickel typecheck **/*.ncl  # type errors stay reported, never auto-applied.
```

### Scope

Every `*.ncl` file under the repo root, excluding any path in `.gitignore`
and any `target/`, `node_modules/`, or `_artifacts/` directory.
