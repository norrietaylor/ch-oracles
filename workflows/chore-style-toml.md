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
  allowed: [defaults]

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/toml-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/toml-build-commands.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  create-issue:
    max: 1
    labels:
      - agent:lint:toml
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:lint:toml
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
    - 'taplo fmt'
    - 'taplo fmt --check'
    - 'taplo lint'
    - 'cat /tmp/previous-findings.json'
    - 'git diff --stat'
    - 'git status'
    - 'gh issue view *'
---

<!--
Behavior summary:
  - `report` runs taplo fmt --check + taplo lint; files one issue.
  - `autofix` runs taplo fmt; opens a PR.
  - Do not run on Cargo.toml in Rust workspaces (covered by chore-style-rust).
-->

# Style chore: TOML

You are the TOML style agent. Read `inputs.mode` and act accordingly.

## Scope

Every `*.toml` file under the repo root, excluding:

- `target/`, `node_modules/`, paths in `.gitignore`.
- `Cargo.toml` and any TOML file inside a Rust workspace member — those are
  covered by `chore-style-rust.md` via `cargo fmt`.

## Mode: report

1. `taplo fmt --check` — list files needing reformat.
2. `taplo lint` — capture lint findings (schema, key-order, etc.).
3. If both pass, emit `noop` and exit 0.
4. File one issue:

   ```html
   <!-- finding-id: lint::toml::<file-path>::<rule-id-or-section> -->
   ```

   Title: `[lint:toml] <file-path>: <issue-summary>`.

   Body sections:
   - **Findings** — file:line, taplo rule id, message.
   - **Suggested fix** — taplo's proposed diff.
   - **Reproduce locally** — `taplo fmt --check` or `taplo lint`.
   - **Severity** — `LOW` for fmt, `MEDIUM` for lint rule violations.

Apply dedup before emitting.

## Mode: autofix

1. `taplo fmt` (rewrites files in place).
2. **Verification gate**:
   - `taplo fmt --check` — must exit 0.
   - `taplo lint` — must exit 0. If lint fails, do not open the PR
     (taplo lint has no `--fix` mode for schema violations).
3. Open one PR via `create-pull-request`:
   - Title: `[lint:toml] auto-applied taplo fmt`.
   - Body: summary of files touched, `Closes #<n>` if applicable.
   - Labels: `agent:lint:toml`, `agent:autofix`.
   - Auto-merge: NOT enabled.

## Logging

- `chore-style-toml: noop (no findings)`
- `chore-style-toml: report — issue #<n> opened/updated`
- `chore-style-toml: autofix — PR #<n> opened (<file-count> files touched)`
- `chore-style-toml: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not modify `Cargo.toml` or any TOML inside a Rust workspace.
- Do not auto-apply schema-violation fixes; only formatter changes.
- Do not open more than one PR or issue per run.
