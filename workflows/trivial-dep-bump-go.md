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
  allowed: [defaults, go]

env:
  PR_TITLE: 'chore(deps): patch-level Go bumps'

imports:
  - gominimal/ch-oracles/shared/principles.md@main
  - gominimal/ch-oracles/shared/rigor.md@main
  - gominimal/ch-oracles/shared/repo-conventions.md@main
  - gominimal/ch-oracles/shared/safe-output-create-issue.md@main
  - gominimal/ch-oracles/shared/runtime-setup.md@main
  - gominimal/ch-oracles/shared/go-runtime-setup.md@main
  - gominimal/ch-oracles/shared/go-build-commands.md@main

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
  report-incomplete:
    labels:
      - agent:dep-drift

tools:
  github:
    allowed: [list_pull_requests, get_pull_request]
  bash:
    - 'go get -u=patch ./...'
    - 'go mod tidy'
    - 'go list -m -json all'
    - 'go list -u -m all'
    - 'go build ./...'
    - 'go vet ./...'
    - 'go test ./...'
    - 'staticcheck ./...'
    - 'govulncheck ./...'
    - 'gofmt -l .'
    - 'git diff go.mod'
    - 'git diff go.sum'
    - 'git diff --stat'
    - 'git status'
    - 'jq *'
    - 'diff *'
    - 'gh pr list *'
---

<!--
Behavior summary:
  - Patch-level Go module updates.
  - One PR per run with auto-merge enabled.
  - Constraints: no major/minor bump; govulncheck clean; toolchain directive unchanged.
-->

# Trivial dep-bump chore: Go

You are the trivial-dep-bump agent for a Go module. Apply patch-level
updates via `go get -u=patch ./...` followed by `go mod tidy`, open one PR
titled `chore(deps): patch-level Go bumps`.

## Locked "trivial" scope

Reject the run if **any** constraint fails:

1. **Patch-level only.** For each changed module, the version change must
   stay within the same minor (`v1.2.3` → `v1.2.4`). Any minor or major
   bump rejects.
2. **`go.mod` toolchain directive unchanged.** The `go` and `toolchain`
   lines must be identical before and after.
3. **No new direct dependencies added or removed.** Indirect dependencies
   may shift as `go mod tidy` resolves graph changes.
4. **govulncheck reports zero vulnerabilities** of severity `high` or
   `critical` after the upgrade.

## Procedure

1. Pre-run setup captures the pre-update module set and `go.mod` contents.
2. Run `go get -u=patch ./...` then `go mod tidy`.
3. Capture the post-update module set and diff `go.mod`.
4. Evaluate constraints 1-2-3.
5. Run the verification gate from `shared/go-build-commands.md`.
6. Run `govulncheck ./...` and reject if constraint 4 fails.
7. Open one PR via `create-pull-request`:
   - Title: `chore(deps): patch-level Go bumps`.
   - Body: a markdown table of every module updated.
   - Auto-merge enabled declaratively.

## Pre-run setup

```bash
cp go.mod /tmp/go.mod.before
go list -m -json all | jq -r 'select(.Main != true) | .Path + " " + .Version' \
  | sort -u > /tmp/mods-before.txt
```

## Logging

- `trivial-dep-bump-go: PR #<n> opened (<count> modules updated); auto-merge enabled`
- `trivial-dep-bump-go: nothing to update`
- `trivial-dep-bump-go: rejected (<constraint>); no PR opened`
- `trivial-dep-bump-go: prior PR #<n> still open; deferring`

## What you must not do

- Open more than one PR per run.
- Change the `go` or `toolchain` directive in `go.mod`.
- Bypass govulncheck on `high`/`critical` findings.
- Retry within the same day.
