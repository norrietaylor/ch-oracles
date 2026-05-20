# Agent Contract: {{REPO_NAME}}

## Overview

This document defines the ch-oracles agentic-workflow contract for
**{{REPO_NAME}}**. It lists which chore workflows are active, what they are
permitted to do, what labels they emit, and the constraints they honor.

Primary language: **{{LANGUAGE}}**. Source-of-truth:
[`norrietaylor/ch-oracles`](https://github.com/norrietaylor/ch-oracles).

## Active chore workflows

The bootstrap install runs `scripts/quick-setup.sh --suite oracles` against
this repo, writing thin wrapper YAMLs to `.github/workflows/`. Each wrapper
calls a hosted, self-contained `.lock.yml` from
`norrietaylor/ch-oracles/.github/workflows/`. Upgrades pull a newer release
tag via the same script.

| Workflow | Output | Trigger | Applies to |
|---|---|---|---|
| `docs-patrol` | One issue per drift, label `agent:doc-drift` | Weekly Mon + push to main on doc paths | all |
| `test-coverage-detector` | Up to 3 issues for high-complexity untested functions, label `agent:coverage` | Weekly Tue | rust, python, go |
| `dependency-review` | One issue per advisory or major-drift finding, label `agent:dep-drift` | Twice-weekly Tue/Fri | rust, python, go |
| `trivial-dep-bump-<lang>` | One auto-merge PR with patch-level lockfile bumps | Daily | per language |
| `chore-style-<lang>` | One issue (mode: report) or one PR (mode: autofix) per lint finding, label `agent:lint:<lang>` | Weekly Mon | per language |
| `pr-conflict-resolver` | Rebases worker PRs on conflict; applies `needs-human` on refusal | push:main + PR synchronize + 6h backstop | all |
| `worker-fix` | Draft PR fixing one open `agent:*` issue | Daily + reactive `issues.labeled` | all |
| `worker-iterate` | Pushes commits to worker-fix PR branches addressing review feedback | `pull_request_review` on `[worker:` PRs | all |

## Constraints (every chore)

- **Not-gating.** No chore output appears in `required_status_checks`.
  Branch protection depends only on the existing CI. See
  [ADR 0001](https://github.com/norrietaylor/ch-oracles/blob/main/decisions/0001-not-gating.md).
- **Caps.** Audit chores cap at 1 issue per run (3 for
  `test-coverage-detector`); fix chores cap at 1 PR per run. Duplicate
  findings dedup per finding-id marker; re-detection updates the existing
  open issue in place rather than filing a new one.
- **No direct `main` push.** All chore output flows through gh-aw safe
  outputs (issues, draft PRs). No chore runs `git push` or `gh pr merge`
  directly.
- **Issue caps.** Each issue body is capped at 10 `@`-mentions and 50
  links; only the HTML tags listed in `shared/safe-output-create-issue.md`
  are permitted.

## Build Commands (ch-oracles override)

<!-- ch-oracles:build-commands:begin -->

`language: {{LANGUAGE}}`

`build:` <fill in or remove for default>
`test:` <fill in or remove for default>
`lint:` <fill in or remove for default>

<!-- ch-oracles:build-commands:end -->

If this section is removed or left empty, workers fall back to the language
defaults in
[`shared/build-matrix.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/build-matrix.md).
Override here for any project that uses a non-default build invocation
(e.g., `just verify`, custom Makefile target, monorepo subpath).

## Label taxonomy

ch-oracles owns the following label prefixes. Defined in
[`.github/labels.yml`](./labels.yml).

### `agent:*` — chore-output labels (issues opened by audit chores)

| Label | Filed by | What it means |
|---|---|---|
| `agent:lint:rust` | `chore-style-rust` | Rust style/lint finding (rustfmt or clippy) |
| `agent:lint:python` | `chore-style-python` | Python style/lint finding (ruff or mypy) |
| `agent:lint:go` | `chore-style-go` | Go style/lint finding (gofmt or staticcheck) |
| `agent:lint:toml` | `chore-style-toml` | TOML style/lint finding (taplo) |
| `agent:lint:ncl` | `chore-style-ncl` | Nickel style/typecheck finding |
| `agent:doc-drift` | `docs-patrol` | Documentation drift from implementation |
| `agent:coverage` | `test-coverage-detector` | High-complexity function lacks tests |
| `agent:dep-drift` | `dependency-review` | Dependency advisory or major-version drift |

### PR-output labels

| Label | Applied to | What it means |
|---|---|---|
| `agent:auto-merge` | PRs from `trivial-dep-bump-*` | Informational; auto-merge enabled by gh-aw runtime |
| `agent:autofix` | PRs from `chore-style-*` in `mode: autofix` | Auto-applied formatter/lint fixes |
| `agent:conflict` | PRs rebased by `pr-conflict-resolver` | Resolver successfully rebased |

### Hand-off labels

| Label | Applied to | What it means |
|---|---|---|
| `needs-human` | Issues / PRs a chore handed off | A chore reached a state needing human action; the chore will not re-process the item until a human removes the label. |
| `agent:worker-tuning` | Issues against the source repo | Worker exhausted its iteration cap; meta-feedback for tuning. |

## Spectacles coexistence

If this repo also installs
[norrietaylor/spectacles](https://github.com/norrietaylor/spectacles), both
suites coexist:

- spectacles owns the SDD-pipeline-behaviour sections of this file (look for
  `<!-- spectacles:... -->` markers).
- ch-oracles owns the `## Build Commands (ch-oracles override)` section
  (look for `<!-- ch-oracles:build-commands:... -->` markers).
- The `needs-human` label is shared (cross-suite hand-off).

## Updating this document

This file is managed by `scripts/quick-setup.sh` from
[`norrietaylor/ch-oracles`](https://github.com/norrietaylor/ch-oracles).
Rerun the script with `--update` to refresh non-override sections; the
build-commands override section is preserved across runs.
