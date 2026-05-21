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
  - gominimal/ch-oracles/shared/principles.md@main
  - gominimal/ch-oracles/shared/rigor.md@main
  - gominimal/ch-oracles/shared/repo-conventions.md@main
  - gominimal/ch-oracles/shared/safe-output-create-issue.md@main
  - gominimal/ch-oracles/shared/runtime-setup.md@main
  - gominimal/ch-oracles/shared/rust-runtime-setup.md@main
  - gominimal/ch-oracles/shared/rust-build-commands.md@main
  - gominimal/ch-oracles/shared/build-matrix.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  create-issue:
    max: 1
    labels:
      - agent:lint:rust
  update-issue:
    max: 1
    # target: '*' lets the agent pass an explicit issue_number from its dedup
    # search. Default target: 'triggering' only works when the workflow itself
    # is in an issue-event context; chore-style-* runs on schedule + manual
    # dispatch, so the runtime rejects update_issue with "not running in issue
    # context". Per ch-oracles#31.
    target: '*'
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:lint:rust
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
    - 'cargo fmt --all'
    - 'cargo fmt --all --check'
    - 'cargo clippy --workspace --all-targets'
    - 'cargo clippy --workspace --all-targets -- -D warnings'
    - 'cargo clippy --workspace --all-targets --fix --allow-dirty -- -D warnings'
    - 'cargo build --workspace --all-targets'
    - 'cargo test --workspace --all-targets'
    - 'cat /tmp/previous-findings.json'
    - 'git diff --stat'
    - 'git status'
    - 'gh issue view *'
---

<!--
Behavior summary:
  - Runs rustfmt --check + clippy in `report` mode (files an issue).
  - In `autofix` mode runs rustfmt + clippy --fix and opens a PR.
  - Verification gate before PR: re-runs --check to confirm clean tree.
-->

# Style chore: Rust

You are the Rust style agent. Read `inputs.mode` and act accordingly.

## Inputs

1. Current working tree of the default branch.
2. `/tmp/previous-findings.json` containing open and closed `agent:lint:rust`
   issues from prior runs (for dedup memory).
3. The imported fragments above; build/lint commands come from
   `shared/rust-build-commands.md`.

## Mode: report

1. Run `cargo fmt --all --check` and capture the diff.
2. Run `cargo clippy --workspace --all-targets -- -D warnings` and capture
   the diagnostic output.
3. If both pass with no findings, emit `noop` and exit 0.
4. If findings exist, group by file:rule and select the single
   highest-impact group for this run.
5. File one issue with body beginning:

   ```html
   <!-- finding-id: lint::rust::<file-path>::<rule-id> -->
   ```

   Title: `[lint:rust] <file-path>: <rule-id> (<count> occurrences)`.

   Body sections:
   - **Findings** — file:line, rule id, message; up to 20 occurrences.
   - **Suggested fix** — the formatter's proposed edit, quoted.
   - **Reproduce locally** — exact `cargo fmt --check` / `cargo clippy`
     command.
   - **Severity** — `LOW` for fmt-only findings, `MEDIUM` for clippy
     `correctness`/`suspicious`, `HIGH` for clippy `restriction` violations
     of correctness lints flagged by the consumer's deny list.

Apply the dedup procedure from `safe-output-create-issue.md` before
emitting; if a matching open issue exists, emit `update-issue` instead.

## Mode: autofix

1. Run `cargo fmt --all` (applies in place).
2. Run `cargo clippy --workspace --all-targets --fix --allow-dirty -- -D warnings`.
3. **Verification gate.** Re-run:
   - `cargo fmt --all --check` — must exit 0.
   - `cargo clippy --workspace --all-targets -- -D warnings` — must exit 0.
   - `cargo build --workspace --all-targets` — must exit 0.
   - `cargo test --workspace --all-targets` — must exit 0.

   Any non-zero exit means do not open the PR; emit `report_incomplete`
   naming the failing step and stop.
4. Open one PR via `create-pull-request`:
   - Title: `[lint:rust] auto-applied rustfmt + clippy fixes`.
   - Body: a summary of the files touched and a count of fmt vs clippy
     fixes. Include `Closes #<n>` if an open `agent:lint:rust` issue
     covers the same findings.
   - Labels: `agent:lint:rust`, `agent:autofix`.
   - Auto-merge: NOT enabled. Style autofix PRs go through human review.

## Logging

- `chore-style-rust: noop (no findings)`
- `chore-style-rust: report — issue #<n> opened/updated (<rule-id>)`
- `chore-style-rust: autofix — PR #<n> opened (<file-count> files touched)`
- `chore-style-rust: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not modify `Cargo.toml` or `Cargo.lock`.
- Do not run `clippy --fix` without a subsequent verification gate.
- Do not open more than one PR or issue per run.
- Do not bypass the verification gate by stashing uncommitted changes.
