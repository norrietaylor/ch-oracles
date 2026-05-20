# TOML

## Wrappers installed for a TOML consumer

- `chore-style-toml.yml` — `taplo fmt` + `taplo lint`; mode: report |
  autofix.
- Universal wrappers (no dep-bump for TOML; the format itself has no
  dependencies).

## Toolchain provisioning

```yaml
- name: Install taplo
  run: |
    curl -fsSL https://github.com/tamasfe/taplo/releases/latest/download/taplo-linux-x86_64.gz \
      | gunzip > /usr/local/bin/taplo
    chmod +x /usr/local/bin/taplo
```

## Verification commands

Defaults (from `shared/toml-build-commands.md`):

```bash
taplo fmt --check
taplo lint
```

## Network egress

`network.allowed: [defaults]` is sufficient; taplo doesn't fetch
dependencies. The release binary download is hosted on GitHub, covered by
`defaults`.

## Scope and overlap

`chore-style-toml.md` covers every `*.toml` file under the repo root
*except* `Cargo.toml` and any TOML inside a Rust workspace member, which
are covered by `chore-style-rust.md` via `cargo fmt`.

If your repo has both Cargo and non-Cargo TOML files (e.g., a Rust binary
plus a `dprint.toml` config), install both `chore-style-rust.yml` and
`chore-style-toml.yml`. They will not conflict — they operate on disjoint
file sets.

If your repo has *only* Cargo TOML, you can skip installing
`chore-style-toml.yml`; cargo handles formatting.

## Optional configuration

A `.taplo.toml` config file at the repo root is honored when present.
Otherwise default schema and rules apply.
