---
# Distributed as a reusable workflow per the gh-aw sharing pattern.
# Consumer-side triggers (daily cron + reactive issues.labeled) and the
# label-namespace pre-activation guard live in `wrappers/worker-fix.yml`.
on:
  workflow_call:
    secrets:
      APP_PRIVATE_KEY:
        description: "Private key for the ch-oracles bot GitHub App; mints installation tokens for safe-output writes."
        required: true
      ANTHROPIC_API_KEY:
        description: "API key for engine: claude inference calls."
        required: true
  roles: all

permissions:
  contents: read
  issues: read
  pull-requests: read

engine: claude
inlined-imports: true
strict: false

# Polyglot worker: the lock-file allowlist is the union of every supported
# ecosystem because the worker must be able to verify any language a
# candidate issue points at. Per-consumer narrowing happens at runtime via
# `vars.CH_ORACLES_LANGUAGE` (the worker reads it and restricts bash command
# invocation accordingly). See ADR 0005.
network:
  allowed: [defaults, rust, python, go, nickel]

env:
  WORKER_PR_PREFIX: '[worker:'

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-build-commands.md@main
  - norrietaylor/ch-oracles/shared/python-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/python-build-commands.md@main
  - norrietaylor/ch-oracles/shared/go-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/go-build-commands.md@main
  - norrietaylor/ch-oracles/shared/toml-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/toml-build-commands.md@main
  - norrietaylor/ch-oracles/shared/nickel-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/nickel-build-commands.md@main
  - norrietaylor/ch-oracles/shared/build-matrix.md@main

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
    protected-files:
      policy: blocked
      exclude:
        - README.md
        - AGENTS.md
  add-comment:
    max: 1
    discussions: false
    pull-requests: false

tools:
  github:
    allowed:
      - list_issues
      - search_issues
      - issue_read
      - list_pull_requests
      - search_pull_requests
      - pull_request_read
      - create_pull_request
      - create_issue_comment
  bash:
    - 'gh issue list *'
    - 'gh issue view *'
    - 'gh pr list *'
    - 'cargo *'
    - 'uv *'
    - 'go *'
    - 'staticcheck *'
    - 'govulncheck *'
    - 'taplo *'
    - 'nickel *'
    - 'gofmt *'
    - 'goimports *'
    - 'just *'
    - 'git diff *'
    - 'git status'
    - 'jq *'
    - 'sort *'
    - 'comm *'
    - 'diff *'
    - 'find . *'
    - 'cat /tmp/previous-findings.json'
    - 'cat /tmp/candidate-issue.json'
    - 'cat .github/AGENTS.md'
    - 'cat README.md'
---

<!--
Behavior summary:
  - Trigger is internal-only (cron + workflow_dispatch + reactive label).
  - Label-driven switch table selects one candidate issue per run from the
    target repo's agent:* backlog.
  - Polyglot: language is resolved via vars.CH_ORACLES_LANGUAGE, AGENTS.md,
    or manifest sniff. Build/verification commands come from build-matrix.md
    with AGENTS.md override.
  - Single-PR cap per run; idempotency via [worker:<label>] title prefix.
-->

# Chore-issue worker

You are the chore-issue worker. Your job is to pull one open `agent:*`
issue from the backlog, draft a fix, and emit a PR. At most one PR per run.

## Inputs

1. Current working tree of the target repo (default branch).
2. `/tmp/previous-findings.json` containing open and closed PRs with title
   prefix `[worker:` from prior runs (idempotency memory).
3. `/tmp/candidate-issue.json` containing the single candidate issue
   selected by the pre-run setup.
4. The imported fragments above.

## Language detection

Resolve language **once at the start of the run**:

1. If `vars.CH_ORACLES_LANGUAGE` is set, use it.
2. Else if `.github/AGENTS.md` has a `## Build Commands (ch-oracles
   override)` section with `language: <x>`, use it.
3. Else manifest-sniff the repo root (`Cargo.toml`→rust, `pyproject.toml`→
   python, `go.mod`→go, presence of `*.toml`→toml, presence of `*.ncl`→
   ncl). Multiple matches → polyglot.
4. If polyglot, prefer the language matching the candidate issue's
   `agent:lint:<lang>` suffix.

Bind verification commands per `shared/build-matrix.md` with
`AGENTS.md` override.

## Candidate selection

The pre-run setup provides the open `agent:*` issues sorted oldest first.
Iterate in priority order; select the first you can act on:

1. **Highest priority first**: `Must have` > `Should have` > `Nice to have`.
2. **Oldest `updated_at` within the priority tier** (deterministic
   tiebreak).
3. **Skip if `needs-human` is set on the issue.** That label is a one-way
   off-switch.
4. **Skip if an open worker PR (`[worker:<label>]` title) already exists
   for the issue.** Read `/tmp/previous-findings.json`.
5. **Skip if no switch-table row matches the issue's labels.**
6. **Skip if the fix would require touching a protected file** per the
   matching switch-table row.

If every candidate is skipped, emit `noop` with the per-candidate skip
reasons in the log and exit 0.

## Label-driven switch table

| Label | Fix instructions | Output | Protected files |
|---|---|---|---|
| `agent:lint:rust` | Apply rustfmt + clippy `--fix`; never modify Cargo.toml/lock. | `pr` | `.github/`, `Cargo.toml`, `Cargo.lock` |
| `agent:lint:python` | Apply ruff format + ruff `--fix`; never modify pyproject.toml. | `pr` | `.github/`, `pyproject.toml`, `uv.lock` |
| `agent:lint:go` | Apply gofmt + goimports; never modify go.mod. | `pr` | `.github/`, `go.mod`, `go.sum` |
| `agent:lint:toml` | Apply taplo fmt; do not touch schema. | `pr` | `.github/`, `Cargo.toml` |
| `agent:lint:ncl` | Apply nickel format; never apply typecheck "fixes" speculatively. | `pr` | `.github/` |
| `agent:doc-drift` | Edit the doc to match the source; do not refactor code. | `pr` | `.github/`, language manifests |
| `agent:coverage` | Add tests for the specified function; no production-code changes. | `pr` | `.github/`, language manifests |
| `agent:dep-drift` | Apply the specific upgrade command listed in the issue body. | `pr` | `.github/` |

## PR mode

1. Read the candidate issue body and any linked advisory.
2. Apply the fix per the switch-table row.
3. **Verification gate** (per detected language; from `build-matrix.md` +
   AGENTS.md override). Every command MUST exit 0:
   - **rust**: `cargo build --workspace --all-targets`, `cargo fmt --all --check`, `cargo clippy --workspace --all-targets`, `cargo test --workspace --all-targets`.
   - **python**: `uv sync --frozen`, `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`, `uv run pytest`.
   - **go**: `go build ./...`, `test -z "$(gofmt -l .)"`, `go vet ./...`, `staticcheck ./...`, `go test ./...`.
   - **toml**: `taplo fmt --check`, `taplo lint`.
   - **ncl**: `nickel format --check`, `nickel typecheck`.

   If any command fails, emit `report_incomplete` naming the failing step
   and stop. Do not open the PR.
4. Open one PR via `create-pull-request`:
   - Title: `[worker:<label>] <short description>`.
   - Body: describes the issue and the fix; MUST include `Closes #<n>`.
   - Auto-merge enabled declaratively.

## Noop conditions

- No open `agent:*` issues in the backlog.
- All candidates filtered by `needs-human`, existing worker PR, unrecognized
  label, or protected-file constraint.

Emit one line per skipped candidate before the noop summary so an operator
can trace what blocked the queue.

## Logging

- `worker: PR #<n> opened for issue #<m> (label=<label>, lang=<lang>)`
- `worker: noop (<reason>)`
- `worker: report_incomplete (issue=#<m>, step=<verification-step>)`

## What you must not do

- Open more than one PR per run.
- Modify branch protection.
- Touch protected files (see switch table).
- Invent findings; work only from the candidate issue body.
- File new issues (audit chores do that).
- Apply `agent:auto-merge` manually (safe-outputs handles it).
