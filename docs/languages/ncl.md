# Nickel (`.ncl`)

## Wrappers installed for a Nickel consumer

- `chore-style-ncl.yml` — `nickel format` + `nickel typecheck`; mode:
  report | autofix.
- Universal wrappers (no dep-bump for Nickel today).

## Toolchain provisioning

```yaml
- name: Install nickel
  run: |
    curl -fsSL https://github.com/tweag/nickel/releases/latest/download/nickel-x86_64-linux \
      -o /usr/local/bin/nickel
    chmod +x /usr/local/bin/nickel
```

## Verification commands

Defaults (from `shared/nickel-build-commands.md`):

```bash
nickel format --check **/*.ncl
nickel typecheck **/*.ncl
```

## Network egress

`network.allowed: [defaults, nickel]` unions in `nickel-lang.org` and the
release host on `github.com/tweag/nickel`.

If your Nickel files use `import` directives to fetch external contracts,
the host serving those contracts must be added to the consumer's network
allowlist via repository configuration (open an issue if you need this
codified into the lock file).

## Limitations

- Typecheck failures in `mode: autofix` block the PR. Type errors are
  semantic; ch-oracles does not attempt to "fix" them.
- No `chore-tidy-ncl` exists; the format + typecheck combination is the
  full lint scope.
