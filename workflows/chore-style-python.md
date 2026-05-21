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
  allowed: [defaults, python]

imports:
  - gominimal/ch-oracles/shared/principles.md@main
  - gominimal/ch-oracles/shared/rigor.md@main
  - gominimal/ch-oracles/shared/repo-conventions.md@main
  - gominimal/ch-oracles/shared/safe-output-create-issue.md@main
  - gominimal/ch-oracles/shared/runtime-setup.md@main
  - gominimal/ch-oracles/shared/python-runtime-setup.md@main
  - gominimal/ch-oracles/shared/python-build-commands.md@main
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
      - agent:lint:python
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    labels:
      - agent:lint:python
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
    - 'uv sync --frozen'
    - 'uv run ruff format'
    - 'uv run ruff format --check'
    - 'uv run ruff check'
    - 'uv run ruff check --fix'
    - 'uv run mypy'
    - 'uv run pytest'
    - 'cat /tmp/previous-findings.json'
    - 'git diff --stat'
    - 'git status'
    - 'gh issue view *'
---

<!--
Behavior summary:
  - `report` runs ruff format --check + ruff check + mypy; files one issue.
  - `autofix` runs ruff format + ruff check --fix; opens a PR.
  - mypy findings stay reported; never auto-applied (no --fix mode).
-->

# Style chore: Python

You are the Python style agent. Read `inputs.mode` and act accordingly.

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

1. `uv sync --frozen` to provision the environment.
2. `uv run ruff format --check` — capture format diff.
3. `uv run ruff check` — capture lint findings.
4. `uv run mypy` — capture type errors.
5. If all three pass with no findings, emit `noop` and exit 0.
6. Pick the single highest-impact finding group (by occurrence count) and
   file one issue:

   ```html
   <!-- finding-id: lint::python::<file-path>::<rule-id-or-error-code> -->
   ```

   Title: `[lint:python] <file-path>: <rule-id> (<count> occurrences)`.

   Body sections:
   - **Findings** — file:line, rule/code, message; up to 20 occurrences.
   - **Suggested fix** — ruff or mypy's proposed edit, where available.
   - **Reproduce locally** — exact `uv run ruff` / `uv run mypy` command.
   - **Severity** — `LOW` for ruff format, `MEDIUM` for ruff check rules,
     `HIGH` for mypy `error` (not `note` or `warning`).

Apply dedup before emitting.

## Mode: autofix

1. `uv sync --frozen`.
2. `uv run ruff format` (applies in place).
3. `uv run ruff check --fix` (applies fixable lints).
4. **Verification gate**:
   - `uv run ruff format --check` — must exit 0.
   - `uv run ruff check` — must exit 0.
   - `uv run mypy` — must exit 0. **If mypy fails, do not open the PR**
     even if ruff is clean; mypy has no `--fix` mode and unfixed type
     errors carry semantic risk.
   - `uv run pytest` — must exit 0.
5. Open one PR via `create-pull-request` (safe-output tool
   `create_pull_request`). **Do not call `create_issue` in this mode** —
   see the contract above.
   - Title: `[lint:python] auto-applied ruff format + lint fixes`.
   - Body: summary of files touched, count of format vs lint fixes,
     `Closes #<n>` if a matching `agent:lint:python` issue is open.
   - Labels: `agent:lint:python`, `agent:autofix`.
   - Auto-merge: NOT enabled.

## Logging

- `chore-style-python: noop (no findings)`
- `chore-style-python: report — issue #<n> opened/updated (<rule-id>)`
- `chore-style-python: autofix — PR #<n> opened (<file-count> files touched)`
- `chore-style-python: autofix — report_incomplete (<failing-step>)`

## What you must not do

- Do not modify `pyproject.toml` or `uv.lock`.
- Do not auto-apply mypy fixes (mypy has no `--fix` mode; do not synthesize one).
- Do not open more than one PR or issue per run.
- Do not skip the pytest verification step in autofix mode.
- Do not call `create_issue` or `update_issue` when `inputs.mode == autofix`.
- Do not call `create_pull_request` when `inputs.mode == report`.
