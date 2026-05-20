## Build matrix

This fragment is the canonical source for default per-language verification
commands. Workers and lint chores import it to know how to build, test, and
lint a consumer repo without baking the commands into the workflow body.

### Resolution order

1. **`AGENTS.md` override.** If the consumer repo's `.github/AGENTS.md` has
   a `## Build Commands (ch-oracles override)` section, treat it as
   authoritative. Parse its YAML-ish key:value lines.
2. **`vars.CH_ORACLES_LANGUAGE` repository variable.** If set, restrict the
   language to the named value. Valid: `rust | python | go | toml | ncl | polyglot`.
3. **Manifest sniff.** If neither override is present, detect language(s)
   from the repo root:
   - `Cargo.toml` → rust
   - `pyproject.toml` → python
   - `go.mod` → go
   - Presence of `*.toml` files (and no other primary language) → toml
   - Presence of `*.ncl` files → ncl
   - Multiple matches → polyglot
4. **Defaults below.** Apply the row matching the resolved language.

### Defaults

| Language | build | test | lint |
|---|---|---|---|
| rust | `cargo build --workspace --all-targets` | `cargo test --workspace --all-targets` | `cargo fmt --all --check && cargo clippy --workspace --all-targets` |
| python | `uv sync` | `uv run pytest` | `uv run ruff format --check && uv run ruff check && uv run mypy` |
| go | `go build ./...` | `go test ./...` | `gofmt -l . && go vet ./... && staticcheck ./...` |
| toml | _(no-op)_ | _(no-op)_ | `taplo fmt --check && taplo lint` |
| ncl | _(no-op)_ | _(no-op)_ | `nickel format --check && nickel typecheck` |

For `polyglot`, run the union of every matched language's commands in order
(rust → python → go → toml → ncl). Any non-zero exit fails the gate.

### AGENTS.md override schema

```markdown
## Build Commands (ch-oracles override)

language: rust          # rust | python | go | toml | ncl | polyglot
build: just verify
test: just test
lint: just lint
```

Keys are required: `language`, `build`, `test`, `lint`. Values are shell
commands evaluated in the repo root. The agent does not invoke a separate
parser — it reads the section as text and substitutes the listed commands
verbatim into its verification gate.

### Verification gate behavior

Before opening any PR, the worker runs `build && test && lint` (resolved per
above) and confirms each command exits 0. Any non-zero exit means do not
open the PR; emit `report_incomplete` naming the failing step and stop.
