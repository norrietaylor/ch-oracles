## TOML runtime setup

For workflows that lint or format TOML files, install `taplo`.

### Install taplo

```yaml
- name: Install taplo
  run: |
    curl -fsSL https://github.com/tamasfe/taplo/releases/latest/download/taplo-linux-x86_64.gz \
      | gunzip > /usr/local/bin/taplo
    chmod +x /usr/local/bin/taplo
```

### Network egress

This workflow's lock file MUST declare:

```yaml
network:
  allowed: [defaults]
```

`defaults` is sufficient: taplo itself does not fetch dependencies. The
release binary download host (`github.com/tamasfe/taplo`) is included in
`defaults`.

### Tool checks

```bash
command -v taplo >/dev/null 2>&1 || { echo "taplo not found" >&2; exit 1; }
taplo --version
```

### Optional: `.taplo.toml` configuration

If the consumer repo has `.taplo.toml` at the root, taplo honors it.
Otherwise the default schema and rules apply.
