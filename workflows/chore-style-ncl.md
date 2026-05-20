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
  allowed: [defaults, nickel]

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/nickel-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/nickel-build-commands.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  create-issue:
    max: 1
    labels:
      - agent:lint:ncl
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:lint:ncl
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
    - 'nickel format *'
    - 'nickel typecheck *'
    - 'find . -name *.ncl *'
    - 'cat /tmp/previous-findings.json'
    - 'git diff --stat'
    - 'git status'
    - 'gh issue view *'
---

<!--
Behavior summary:
  - `report` runs nickel format --check + nickel typecheck; files one issue.
  - `autofix` runs nickel format; opens a PR.
  - Type errors stay reported; never auto-applied.
-->

# Style chore: Nickel

You are the Nickel style agent. Read `inputs.mode` and act accordingly.

## Scope

Every `*.ncl` file under the repo root, excluding paths in `.gitignore` and
any `target/`, `node_modules/`, or `_artifacts/` directories.

## Mode: report

1. Collect target files: `find . -name '*.ncl' -not -path './target/*' -not -path './node_modules/*' -not -path './_artifacts/*'`.
2. `nickel format --check` on each — capture diffs.
3. `nickel typecheck` on each — capture type errors.
4. If both pass, emit `noop` and exit 0.
5. File one issue:

   ```html
   <!-- finding-id: lint::ncl::<file-path>::<issue-kind> -->
   ```

   Title: `[lint:ncl] <file-path>: <issue-summary>`.

   Body sections:
   - **Findings** — file:line, nickel diagnostic, message.
   - **Suggested fix** — for format, the proposed diff; for typecheck, the
     diagnostic and a one-line correction proposal.
   - **Reproduce locally** — exact `nickel format --check` /
     `nickel typecheck` command.
   - **Severity** — `LOW` for format, `HIGH` for typecheck errors.

Apply dedup before emitting.

## Mode: autofix

1. `nickel format` on each in-scope file (rewrites in place).
2. **Verification gate**:
   - `nickel format --check` on each file — must exit 0.
   - `nickel typecheck` on each file — must exit 0. **If typecheck fails,
     do not open the PR**; type errors are reported, not auto-fixed.
3. Open one PR via `create-pull-request`:
   - Title: `[lint:ncl] auto-applied nickel format`.
   - Body: summary of files touched, `Closes #<n>` if applicable.
   - Labels: `agent:lint:ncl`, `agent:autofix`.
   - Auto-merge: NOT enabled.

## Logging

- `chore-style-ncl: noop (no findings)`
- `chore-style-ncl: report — issue #<n> opened/updated`
- `chore-style-ncl: autofix — PR #<n> opened (<file-count> files touched)`
- `chore-style-ncl: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not auto-apply typecheck fixes.
- Do not open more than one PR or issue per run.
- Do not modify files outside the in-scope set.
