# Copilot instructions for {{REPO_NAME}}

This file is installed by ch-oracles and provides guidance to GitHub Copilot
(used as the `engine: copilot` backend for chore workflows).

## Doc surface

`.github/AGENTS.md` is the canonical contract for this repository. Read it
before proposing changes; the build/test/lint commands declared there
override the language defaults in
[`shared/build-matrix.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/build-matrix.md).

## Behavior

- Apply the principles in
  [`shared/principles.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/principles.md):
  think before acting, simplicity first, surgical changes, goal-driven
  execution.
- Apply the rigor checklist in
  [`shared/rigor.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/rigor.md)
  before filing any issue or opening any PR.
- Never modify branch protection or `required_status_checks`.
- Never push directly to `main`.
- Honor the `needs-human` label as a one-way off-switch on issues and PRs.

## Per-finding dedup

When filing an issue, the body must begin with a finding-id marker:

```html
<!-- finding-id: <chore>::<lang>::<identity> -->
```

Search open issues for a matching marker before filing; if found, update
the existing issue instead of creating a new one.

## Reporting

For findings, follow the issue-body structure in
[`shared/safe-output-create-issue.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/safe-output-create-issue.md):
title, finding-id marker, evidence, suggested action, severity, priority.
