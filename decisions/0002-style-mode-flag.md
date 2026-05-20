# 0002 — Style chores use a `mode` input, not two workflows

Status: Accepted
Date: 2026-05-19

## Context

Lint chores need to support two output modes:

- **`report`** — file an issue describing the finding; do not modify code.
- **`autofix`** — apply the formatter/linter's fixes, verify, open a PR.

Two shapes were considered:

1. **Two workflows per language** (`chore-style-rust-report.md`,
   `chore-style-rust-autofix.md`).
2. **One workflow per language with a `mode:` input** (`chore-style-rust.md`,
   invoked with `inputs.mode=report` or `inputs.mode=autofix`).

A separate axis was also considered: `lint` (style/format) vs `tidy`
(deeper static analysis like clippy `--restriction` or mypy `--strict`).

## Decision

One workflow per language, parameterized by `mode: report | autofix`. No
separate `lint` vs `tidy` split. Each chore-style-* workflow internally
runs the language's formatter AND its static analysis tool, then branches
on `mode`.

## Rationale

- **Fewer files to install.** A consumer gets one wrapper per language,
  not two or four. Auto-detect produces a cleaner install.
- **Shared prompt body.** The selection logic, dedup contract, and
  verification gate are identical across modes. A `mode` branch in the
  prompt body is much shorter than duplicating a workflow.
- **Lint vs tidy is artificial for most languages.** `ruff format` and
  `ruff check --fix` share infrastructure; splitting them produces two
  workflows that always run together. For taplo and nickel, there is no
  separate tidy tier worth shipping. The few languages where deeper
  analysis is meaningfully distinct (rust clippy `--restriction`, go
  staticcheck `SA*` vs `S*`) can be controlled by linter configuration in
  the consumer repo, not by chore split.

## Consequences

- The 5 lint chores ship as 5 workflows, not 10 or 20.
- Schedule cadence is the same across modes; users invoke `autofix` via
  `workflow_dispatch` with an input override, not a separate cron.
- The reserved `agent:tidy:<lang>` label namespace stays unused at v0.
  Future deeper-analysis chores can adopt it without a label rename.
