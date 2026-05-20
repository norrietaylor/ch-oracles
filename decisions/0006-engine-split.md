# 0006 — Engine split: Copilot for chores, Claude for workers

Status: Accepted
Date: 2026-05-19

## Context

gh-aw supports multiple inference backends:

- **`engine: copilot`** — GitHub Copilot Business; requires
  `COPILOT_GITHUB_TOKEN`. Cheaper per call; integrates with GitHub-native
  context.
- **`engine: claude`** — Anthropic API; requires `ANTHROPIC_API_KEY`.
  Higher reasoning capability on multi-step refactor tasks; supports the
  full Claude model tier.

A choice is required per workflow at compile time.

## Decision

- **Chores (audit + lint + dep-bump): `engine: copilot`.**
  - `docs-patrol`, `test-coverage-detector`, `dependency-review`
  - `chore-style-rust`, `chore-style-python`, `chore-style-go`,
    `chore-style-toml`, `chore-style-ncl`
  - `trivial-dep-bump-rust`, `trivial-dep-bump-python`,
    `trivial-dep-bump-go`
- **Workers: `engine: claude`.**
  - `worker-fix`
  - `worker-iterate`
  - `pr-conflict-resolver`

## Rationale

- **Chores are pattern-matching with narrow scope.** Detecting drift,
  finding untested functions, applying patch-level dep bumps — each task
  is well-bounded and benefits more from cost efficiency than from peak
  reasoning. Copilot handles these confidently at lower per-run cost.
- **Workers do multi-step refactors with verification loops.** A worker
  must read the issue, plan the fix, apply it, run the verification
  gate, interpret errors, possibly retry, and produce a clean PR. This
  is multi-step reasoning with non-trivial branching; Claude's
  performance on this class of task justifies the higher per-call cost.
- **Cost concentration.** Most ch-oracles activity is chore runs
  (multiple per repo per week); worker runs are bursty (only when an
  issue is filed or a review comment lands). Concentrating Claude usage
  on the worker tier matches the "expensive thinking, cheap pattern
  matching" pattern.

## Consequences

- Consumer repos must configure two secrets: `COPILOT_GITHUB_TOKEN` (for
  chores) and `ANTHROPIC_API_KEY` (for workers). `quick-setup.sh` prompts
  for both at install time.
- Per-tier model selection is the right knob if Claude's pricing changes
  significantly: a future revision could move audit chores onto Claude
  (or vice versa) by changing the `engine:` field in the affected
  workflows.
- A consumer that does not want one engine can elect not to install the
  corresponding workflows: omit `--with-workers` to skip the Claude-using
  chores entirely.
