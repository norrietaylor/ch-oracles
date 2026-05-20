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

`network.allowed: [defaults]` is sufficient for fetching the Nickel binary
release from GitHub. If your Nickel files use `import` directives to fetch
external contracts (e.g., from `nickel-lang.org`), add the host as an
explicit domain entry in the consumer-side configuration.

## Limitations

- Typecheck failures in `mode: autofix` block the PR. Type errors are
  semantic; ch-oracles does not attempt to "fix" them.
- No `chore-tidy-ncl` exists; the format + typecheck combination is the
  full lint scope.
