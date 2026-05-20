# Rust

## Wrappers installed for a Rust consumer

- `chore-style-rust.yml` — `cargo fmt` + `cargo clippy`; mode: report | autofix.
- `trivial-dep-bump-rust.yml` — patch-level `Cargo.lock` updates with
  auto-merge.
- Universal wrappers (docs-patrol, dep-review, coverage detector, workers).

## Toolchain provisioning

Per `shared/rust-runtime-setup.md`:

```yaml
- uses: dtolnay/rust-toolchain@stable
  with:
    components: rustfmt, clippy
- uses: Swatinem/rust-cache@v2
```

If the consumer's `rust-toolchain.toml` pins a specific channel, it is
honored.

## Verification commands

Defaults (from `shared/rust-build-commands.md`):

```bash
cargo build --workspace --all-targets
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace --all-targets
```

Override these per-repo via the `## Build Commands (ch-oracles override)`
section in `.github/AGENTS.md`. Example for a repo that uses `just`:

```markdown
## Build Commands (ch-oracles override)

language: rust
build: just verify
test: just test
lint: just lint
```

## Network egress

The Rust chore's lock file declares `network.allowed: [defaults, rust]`,
unioning in `crates.io`, `static.crates.io`, and `index.crates.io` on top
of the GitHub-related default endpoints.

## Limitations

- Patch-level dep-bump rejects any change to `Cargo.toml`. Only
  `Cargo.lock` may differ between the pre-update and post-update states.
- Transitive crate additions or removals reject the bump (a patch-level
  change should not add a new crate to the dependency graph).
- Yanked-crate detection runs via `cargo update --dry-run`; the chore
  rejects rather than warn.
