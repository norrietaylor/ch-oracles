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
  allowed: [defaults]
```

`defaults` covers the GitHub release host on `github.com/tweag/nickel`,
which is sufficient to install the binary. The Nickel language does not
have a dedicated gh-aw ecosystem identifier. If your Nickel files import
contracts from `nickel-lang.org` or another host, add the host as an
explicit domain entry:

```yaml
network:
  allowed: [defaults, "nickel-lang.org"]
```

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
