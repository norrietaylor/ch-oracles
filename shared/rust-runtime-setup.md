## Rust runtime setup

For workflows that operate on a Rust workspace, provision the toolchain before
the agent step begins.

### Install rustup with the workspace toolchain

```yaml
- uses: dtolnay/rust-toolchain@stable
  with:
    components: rustfmt, clippy

- uses: Swatinem/rust-cache@v2
  with:
    save-if: ${{ github.ref == 'refs/heads/main' }}
```

If `rust-toolchain.toml` is present at the repo root, `dtolnay/rust-toolchain`
honors its channel and components. Always install `rustfmt` and `clippy`;
both lint and worker chores require them.

### Network egress

This workflow's lock file MUST declare:

```yaml
network:
  allowed: [defaults, rust]
```

The `rust` ecosystem id unions in `crates.io`, `static.crates.io`, and
`index.crates.io`. `defaults` covers GitHub API endpoints.

### Tool checks

```bash
command -v cargo >/dev/null 2>&1 || { echo "cargo not found" >&2; exit 1; }
command -v rustfmt >/dev/null 2>&1 || { echo "rustfmt not found" >&2; exit 1; }
cargo --version
rustc --version
```

### Optional: cargo-llvm-cov for coverage chores

Only the `test-coverage-detector` chore needs this binary:

```yaml
- uses: taiki-e/install-action@v2
  with:
    tool: cargo-llvm-cov
```
