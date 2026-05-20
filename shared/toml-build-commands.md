## TOML build commands

Default lint commands for TOML files. There is no "build" or "test" step for
TOML on its own — the language has no execution model — so these reduce to
lint.

### Verification gate

```bash
taplo fmt --check
taplo lint
```

`taplo fmt --check` exits non-zero if any file needs reformatting.
`taplo lint` validates schema and key conventions.

### Lint commands

`mode: report`:

```bash
taplo fmt --check
taplo lint
```

`mode: autofix`:

```bash
taplo fmt              # rewrites files in place
taplo lint             # lint findings stay reported, never auto-applied.
```

### Scope

ch-oracles' TOML chore covers every `*.toml` file under the repo root,
excluding `target/`, `node_modules/`, and any path in `.gitignore`.

Note: `Cargo.toml` files in a Rust workspace are also covered by
`chore-style-rust.md` via `cargo fmt`. The two chores produce overlapping
findings when both are installed. Prefer `chore-style-rust.md` for Rust
repos and skip `chore-style-toml.md` there; install `chore-style-toml.md`
only when the repo uses TOML outside a Cargo context (config files, Hugo,
etc.).
