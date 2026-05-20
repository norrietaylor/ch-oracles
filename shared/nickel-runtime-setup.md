## Nickel runtime setup

For workflows that lint or typecheck Nickel (`.ncl`) files, install the
`nickel` binary.

### Install nickel

```yaml
- name: Install nickel
  run: |
    curl -fsSL https://github.com/tweag/nickel/releases/latest/download/nickel-x86_64-linux \
      -o /usr/local/bin/nickel
    chmod +x /usr/local/bin/nickel
```

### Network egress

This workflow's lock file MUST declare:

```yaml
network:
  allowed: [defaults, nickel]
```

The `nickel` ecosystem id covers `nickel-lang.org` and the release host on
`github.com/tweag/nickel`.

### Tool checks

```bash
command -v nickel >/dev/null 2>&1 || { echo "nickel not found" >&2; exit 1; }
nickel --version
```

### Optional: imported contracts

If the repo imports contracts via `import "..."` Nickel directives, the
agent must have network access to the import sources. Limit the network
egress block to the specific hosts declared in the consumer's `AGENTS.md`
under `## Nickel Imports`.
