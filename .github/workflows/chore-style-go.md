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
  allowed: [defaults, go]

imports:
  - gominimal/ch-oracles/shared/principles.md@main
  - gominimal/ch-oracles/shared/rigor.md@main
  - gominimal/ch-oracles/shared/repo-conventions.md@main
  - gominimal/ch-oracles/shared/safe-output-create-issue.md@main
  - gominimal/ch-oracles/shared/runtime-setup.md@main
  - gominimal/ch-oracles/shared/go-runtime-setup.md@main
  - gominimal/ch-oracles/shared/go-build-commands.md@main
  - gominimal/ch-oracles/shared/build-matrix.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  # Note (issue #30): both create-issue and create-pull-request are listed
  # so the agent has the right tool available in either mode. The agent
  # MUST select the tool that matches inputs.mode — see the prose contract
  # below. Gating via templated `max` was attempted but rejected: every
  # available gh-aw expression form for a ternary (`cond && '0' || '1'`,
  # `fromJSON('{"k":"v"}')[inputs.x]`) renders into the safe-outputs JSON
  # env var with characters that actionlint cannot lex (`&&` → `&&`;
  # nested `\"` inside `fromJSON()`). The prose contract is the primary
  # defense; if the agent calls create_issue in autofix anyway, the
  # safe-output allowlist will still create the issue but the chore
  # behaviour is wrong and visible from the run log.
  create-issue:
    max: 1
    labels:
      - agent:lint:go
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:lint:go
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
    - 'gofmt -l .'
    - 'gofmt -w .'
    - 'goimports -l .'
    - 'goimports -w .'
    - 'go vet ./...'
    - 'staticcheck ./...'
    - 'go build ./...'
    - 'go test ./...'
    - 'cat /tmp/previous-findings.json'
    - 'git diff --stat'
    - 'git status'
    - 'gh issue view *'
---

<!--
Behavior summary:
  - `report` runs gofmt -l + go vet + staticcheck; files one issue.
  - `autofix` runs gofmt -w + goimports -w; opens a PR.
  - go vet and staticcheck findings stay reported; never auto-applied.
-->

# Style chore: Go

You are the Go style agent. Read `inputs.mode` and act accordingly.

## Mode → safe-output contract (READ FIRST)

The safe-output tool you call MUST match `inputs.mode`. Picking the wrong
tool is the defect tracked in issue #30 and is the single most important
rule in this prompt.

- `mode == report`:
  - You MUST call `create_issue` (or `update_issue` on dedup hit).
  - You MUST NOT call `create_pull_request`. Report mode does not modify
    files; opening a PR is a contract violation.
- `mode == autofix`:
  - You MUST call `create_pull_request`.
  - You MUST NOT call `create_issue` or `update_issue` under any
    circumstances — not as a fallback, not to "also notify", not because
    the verification gate failed. If the verification gate fails, emit
    `report_incomplete` and stop; do not file a new issue.
  - Even though `create_issue` appears in the safe-outputs allowlist
    (so report mode can use it), calling it from autofix is a contract
    violation tracked by issue #30. The wrong-tool behaviour is visible
    in the run log and treated as a defect.

If you find yourself about to call `create_issue` while `inputs.mode ==
autofix`, stop and re-read this section.

## Mode: report

1. `gofmt -l .` — list files needing format (empty output means clean).
2. `goimports -l .` — list files needing import reorder.
3. `go vet ./...` — capture vet findings.
4. `staticcheck ./...` — capture staticcheck findings.
5. If all four are clean, emit `noop` and exit 0.
6. Pick the single highest-impact finding group and file one issue:

   ```html
   <!-- finding-id: lint::go::<file-path>::<rule-id-or-check> -->
   ```

   Title: `[lint:go] <file-path>: <rule-id> (<count> occurrences)`.

   Body sections:
   - **Findings** — file:line, check id (e.g., `SA1006`, `S1000`), message.
   - **Suggested fix** — for gofmt/goimports, the auto-format diff; for
     staticcheck, the upstream recommendation.
   - **Reproduce locally** — exact command.
   - **Severity** — `LOW` for gofmt/goimports, `MEDIUM` for `go vet` and
     staticcheck `S` (style) checks, `HIGH` for staticcheck `SA`
     (correctness) checks.

Apply dedup before emitting.

## Mode: autofix

1. `gofmt -w .` (in-place).
2. `goimports -w .` if installed (skip otherwise).
3. **Verification gate**:
   - `test -z "$(gofmt -l .)"` — must exit 0.
   - `go vet ./...` — must exit 0.
   - `staticcheck ./...` — must exit 0. **If staticcheck fails, do not open
     the PR**; staticcheck has no `--fix` mode and surfaces semantic issues.
   - `go build ./...` — must exit 0.
   - `go test ./...` — must exit 0.
4. Open one PR via `create-pull-request` (safe-output tool
   `create_pull_request`). **Do not call `create_issue` in this mode** —
   see the contract above.
   - Title: `[lint:go] auto-applied gofmt + goimports`.
   - Body: summary of files touched, `Closes #<n>` if applicable.
   - Labels: `agent:lint:go`, `agent:autofix`.
   - Auto-merge: NOT enabled.

## Logging

- `chore-style-go: noop (no findings)`
- `chore-style-go: report — issue #<n> opened/updated (<rule-id>)`
- `chore-style-go: autofix — PR #<n> opened (<file-count> files touched)`
- `chore-style-go: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not modify `go.mod` or `go.sum`.
- Do not auto-apply go vet or staticcheck suggestions.
- Do not open more than one PR or issue per run.
- Do not call `create_issue` or `update_issue` when `inputs.mode == autofix`.
- Do not call `create_pull_request` when `inputs.mode == report`.
