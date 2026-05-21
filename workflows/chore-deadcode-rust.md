---
on:
  workflow_call:
    inputs:
      mode:
        description: 'report (file issue) | autofix (open PR)'
        required: false
        default: 'report'
        type: string
    secrets:
      APP_PRIVATE_KEY: { required: true }
      COPILOT_GITHUB_TOKEN: { required: true }
  roles: all

permissions:
  contents: read
  issues: read
  pull-requests: read

engine: copilot
inlined-imports: true
strict: false

network:
  allowed: [defaults, rust]

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-build-commands.md@main
  - norrietaylor/ch-oracles/shared/build-matrix.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  create-issue:
    max: 1
    labels:
      - agent:deadcode:rust
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:deadcode:rust
      - agent:autofix

tools:
  github:
    allowed:
      - list_issues
      - search_issues
      - issue_read
      - list_pull_requests
      - create_issue_comment
  bash:
    - 'cargo machete --with-metadata'
    - 'cargo machete'
    - 'cargo +nightly udeps --workspace --output json'
    - 'cargo metadata --format-version 1 --no-deps'
    - 'cargo check --workspace --all-targets --message-format=json'
    - 'cargo build --workspace --all-targets'
    - 'cargo test --workspace --all-targets'
    - 'git diff --stat'
    - 'git status'
    - 'cat /tmp/previous-findings.json'
    - 'gh issue view *'
---

<!--
  Source: github/gh-aw/.github/workflows/dead-code-remover.md @ 1924e4f87e36cd2993dfc6b1a3e7f6cb4abc425e
  Bootstrap: 2026-05-21
  Upstream license: MIT, © GitHub, Inc.
  This file is a fork. Not auto-synced. (ADR 0007)
-->

<!--
Behavior summary:
  - Runs cargo-machete and (when nightly available) cargo-udeps to enumerate
    unused workspace dependencies and unreachable items in `report` mode (files
    one issue). Dead-function detection rides on rustc's `dead_code` lint via
    `cargo check --message-format=json`.
  - `autofix` mode removes only high-confidence findings (machete-confirmed
    unused crate-level deps with no test-only callers) and opens one PR.
  - LLM job is gatekeeping — upstream observed only ~31 of 107 detector
    findings were genuinely removable. Triage matters more than detection.
-->

# Dead-code chore: Rust

You are the Rust dead-code chore agent. Read `inputs.mode` and act accordingly.
This chore enumerates candidate dead code (unused dependencies and unreachable
items) and gates the findings against false positives before recommending
removal.

## Inputs

1. Current working tree of the default branch (Rust workspace).
2. `/tmp/previous-findings.json` containing open and closed
   `agent:deadcode:rust` issues from prior runs (dedup memory).
3. The imported fragments above; build/lint commands come from
   `shared/rust-build-commands.md`; toolchain setup from
   `shared/rust-runtime-setup.md`.

## Detector suite

Run the following deterministic detectors and merge their outputs into a
single candidates list before triage:

1. `cargo machete --with-metadata` — unused workspace dependencies.
2. `cargo +nightly udeps --workspace --output json` — unused dependencies and
   unreachable items (nightly toolchain). Skip if nightly is unavailable; do
   not block the run on missing nightly.
3. `RUSTFLAGS="-W dead_code" cargo check --workspace --all-targets --message-format=json`
   — rustc's `dead_code` lint output for unreachable functions, structs,
   variants, and fields.

Combine the candidate set into `/tmp/deadcode-candidates.json`. Each entry
records: `{kind: dep|fn|struct|variant|field, identity, file, line, source: machete|udeps|rustc}`.

## Mode: report

1. Run the detector suite above; build the candidate list.
2. If the list is empty (or every entry was processed and dismissed in a
   prior run), emit `noop` and exit 0.
3. Triage. For each candidate, apply the safety checks:
   - **Test-only callers**: if every caller is in `tests/`, `*_test.rs`, or
     a `#[cfg(test)]` block, the candidate is still dead — keep it.
   - **`#[cfg]`-gated callers**: if a caller sits behind a cfg gate the
     workspace does not currently enable but the gate is referenced in
     `Cargo.toml` features, mark candidate as `cfg-rescued` and skip.
   - **Re-exported via `pub use`**: if the item is re-exported from a
     public module, treat as live (downstream consumers may import).
   - **Bench / example callers**: if a caller sits under `benches/` or
     `examples/`, treat as live — examples are part of the crate surface.
   - **`#[allow(dead_code)]`-annotated**: trust the annotation; skip.
4. Group survivors by identity prefix (crate-level deps first, then
   per-module unreachable items). Select the single highest-confidence
   group for this run (favour `cargo machete` confirmations).
5. File one issue with body beginning:

   ```html
   <!-- finding-id: deadcode::rust::<crate>::<identity> -->
   ```

   Title: `[deadcode:rust] <crate>: <N> candidates (<source>)`.

   Body sections:
   - **Findings** — table of `kind, identity, file:line, source, confidence`.
     Up to 20 rows; link the rest to a full JSON gist if needed.
   - **Triage notes** — for each entry, one line on why it survived safety
     checks.
   - **Recommended removals** — only the entries passing every check above.
     Conservative: prefer false negatives over false positives.
   - **Reproduce locally** — exact detector commands.
   - **Severity** — `LOW` for `dep` kind, `MEDIUM` for `fn`/`struct`/`variant`,
     `HIGH` only when the same identity has been flagged in three or more
     consecutive runs (likely real).

Apply the dedup procedure from `safe-output-create-issue.md` before
emitting; if a matching open issue exists, emit `update-issue` instead.

## Mode: autofix

Conservative removal only.

1. Run the detector suite and triage as in `report` mode.
2. Limit the autofix batch to **at most 5** items, all of which must satisfy:
   - `source: machete` AND `kind: dep`, OR
   - `source: udeps|rustc` AND no test-only callers AND not `pub use`-re-exported.
3. For each `dep` removal, edit `Cargo.toml` to drop the entry.
4. For each unreachable item, delete the item body. Also delete any test
   function that called *only* the removed item.
5. **Verification gate.** Re-run:
   - `cargo build --workspace --all-targets` — must exit 0.
   - `cargo test --workspace --all-targets` — must exit 0.
   - `cargo machete` — the removed deps must no longer appear.

   Any non-zero exit means do not open the PR; emit `report_incomplete`
   naming the failing step and stop.
6. Open one PR via `create-pull-request`:
   - Title: `[deadcode:rust] remove N dead-code candidates (<source-mix>)`.
   - Body: enumerated removals + verification output tail.
   - Body must include `Closes #<n>` if an open `agent:deadcode:rust` issue
     covers the same findings.
   - Labels: `agent:deadcode:rust`, `agent:autofix`.
   - Auto-merge: NOT enabled. Removals go through human review (upstream
     observed ~70% false-positive rate in raw detector output).

## Logging

- `chore-deadcode-rust: noop (no candidates)`
- `chore-deadcode-rust: report — issue #<n> opened/updated (<group-identity>)`
- `chore-deadcode-rust: autofix — PR #<n> opened (<N> removals)`
- `chore-deadcode-rust: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not delete items annotated with `#[allow(dead_code)]`. The annotation is
  authoritative.
- Do not delete items reachable only via examples or benches — they are part
  of the crate surface.
- Do not delete `pub use` re-exports without checking downstream callers.
- Do not modify `Cargo.lock` directly; let `cargo build` regenerate it.
- Do not open more than one PR or issue per run.
- Do not enable auto-merge.
- Do not bypass the verification gate by stashing uncommitted changes.
