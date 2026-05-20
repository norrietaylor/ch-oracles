## Rust build commands

Default verification commands for Rust workspaces. Workers and lint chores
invoke these unless `AGENTS.md` overrides them.

### Verification gate

Every command exits 0 before a PR opens:

```bash
cargo build --workspace --all-targets
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace --all-targets
```

`--workspace` walks every member crate. `--all-targets` covers lib, bins,
tests, examples, and benches. Both flags are required: `--all-targets` alone
only builds the root package's targets, so on a workspace root with both
`[workspace]` and `[package]` it misses every member crate.

Do not invoke `cargo test <pattern>` for verification: a filtered run only
compiles matching tests and masks compile errors in adjacent test files.

### Lint commands

`mode: report`:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
```

`mode: autofix`:

```bash
cargo fmt --all
cargo clippy --workspace --all-targets --fix --allow-dirty -- -D warnings
```

### Dep-bump commands

```bash
cargo update --workspace --dry-run > /tmp/cargo-update-dry-run.log 2>&1
cargo metadata --format-version 1 --locked | jq -r '.packages[].name' | sort -u > /tmp/crates-before.txt
cargo update --workspace
cargo metadata --format-version 1 --locked | jq -r '.packages[].name' | sort -u > /tmp/crates-after.txt
comm -3 /tmp/crates-before.txt /tmp/crates-after.txt  # empty output ⇒ transitive set unchanged
```

A patch-level bump is rejected if the dry-run log contains `warning: yanked`
or if `comm -3` returns non-empty output (transitive crate added or removed).
