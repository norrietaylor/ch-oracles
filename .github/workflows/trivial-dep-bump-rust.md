---
on:
  workflow_call:
    secrets:
      APP_PRIVATE_KEY: { required: true }
      COPILOT_GITHUB_TOKEN: { required: true }

permissions:
  contents: read
  issues: read
  pull-requests: read

engine: copilot
inlined-imports: true
strict: false

network:
  allowed: [defaults, rust]

env:
  PR_TITLE: 'chore(deps): patch-level Cargo bumps'
  AUTO_MERGE_LABEL: 'agent:auto-merge'

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-build-commands.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  create-pull-request:
    max: 1
    draft: ${{ false }}
    auto-merge: true
    labels:
      - agent:auto-merge
      - agent:dep-drift

tools:
  github:
    allowed: [list_pull_requests, get_pull_request]
  bash:
    - 'cargo update --workspace --dry-run'
    - 'cargo update --workspace'
    - 'cargo update -p * --precise *'
    - 'cargo metadata *'
    - 'cargo tree *'
    - 'cargo build --workspace --all-targets'
    - 'cargo fmt --all --check'
    - 'cargo clippy --workspace --all-targets'
    - 'cargo test --workspace --all-targets'
    - 'git diff Cargo.lock'
    - 'git diff --stat'
    - 'git status'
    - 'jq *'
    - 'sort *'
    - 'comm *'
    - 'diff *'
    - 'cat /tmp/cargo-update-dry-run.log'
    - 'cat /tmp/crates-before.txt'
    - 'cat /tmp/crates-after.txt'
    - 'gh pr list *'
---

<!--
Behavior summary:
  - Patch-level Cargo lockfile updates only.
  - One PR per run with auto-merge enabled declaratively via safe-outputs.
  - Constraints: no Cargo.toml diff; no transitive add/remove; no yanked.
-->

# Trivial dep-bump chore: Rust

You are the trivial-dep-bump agent for a Rust workspace. Apply patch-level
updates from `cargo update --workspace`, open a single PR titled
`chore(deps): patch-level Cargo bumps`, label it `agent:auto-merge`, and let
the safe-output runtime enable squash-auto-merge. Consumer CI is the only
gate.

## Locked "trivial" scope

Reject the run and emit a no-op log line if **any** constraint fails. Do not
negotiate, do not partial-apply.

1. **Patch-level Cargo updates only.** `x.y.z` → `x.y.z+1`. Any minor or
   major change is not trivial.
2. **No `Cargo.toml` changes.** The diff must touch `Cargo.lock` only.
3. **No transitive crate added or removed.** The set of crates in the
   lockfile before and after must be identical.
4. **No yanked crate involved.** Check `/tmp/cargo-update-dry-run.log` for
   any `warning: yanked` message.

## Procedure

1. Pre-run setup captures `cargo update --workspace --dry-run` output and
   the pre-update crate set in `/tmp/crates-before.txt`.
2. Run `cargo update --workspace`.
3. Capture the post-update crate set in `/tmp/crates-after.txt`.
4. Evaluate constraint 3: `comm -3 /tmp/crates-before.txt /tmp/crates-after.txt`
   must return empty output.
5. Verify the diff against `git diff Cargo.lock` shows only patch-level
   version mutations; cross-check constraints 1-2-4.
6. Run the verification gate from `shared/rust-build-commands.md`. Every
   command must exit 0 before opening the PR.
7. Open one PR via `create-pull-request`:
   - Title: `chore(deps): patch-level Cargo bumps`.
   - Body: a markdown table of every crate updated (crate, from, to).
   - Auto-merge enabled declaratively; do not invoke `gh pr merge`.

## Pre-run setup

```bash
cargo update --workspace --dry-run > /tmp/cargo-update-dry-run.log 2>&1 || true
cargo metadata --format-version 1 --locked \
  | jq -r '.packages[].name' \
  | sort -u > /tmp/crates-before.txt
```

## Logging

Emit exactly one line:

- `trivial-dep-bump-rust: PR #<n> opened (<count> crates updated); auto-merge enabled`
- `trivial-dep-bump-rust: nothing to update`
- `trivial-dep-bump-rust: rejected (<constraint>); no PR opened`
- `trivial-dep-bump-rust: prior PR #<n> still open; deferring`

## What you must not do

- Open more than one PR per run.
- Modify `Cargo.toml`.
- Bypass auto-merge on CI failure.
- Call `gh pr merge` directly.
- Retry within the same day; the cron handles cadence.
