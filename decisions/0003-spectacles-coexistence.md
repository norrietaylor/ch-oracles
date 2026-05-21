# 0003 — Coexistence with spectacles

Status: Accepted
Date: 2026-05-19

## Context

ch-oracles and [norrietaylor/spectacles](https://github.com/norrietaylor/spectacles)
are sibling suites. spectacles is the spec-driven-development pipeline;
ch-oracles is the chore agent suite. A consumer repo may install one, the
other, or both.

The risk is collision: two suites writing to the same `.github/AGENTS.md`,
applying labels with the same names, or pinning incompatible gh-aw
versions.

## Decision

ch-oracles is designed to **install alongside spectacles without
collision**, by these rules:

1. **Filename disjoint.** ch-oracles wrappers (`chore-style-*.yml`,
   `worker-fix.yml`, etc.) do not collide with spectacles wrappers
   (`sdd-*.yml`, `distillery-sync.yml`).
2. **Label namespacing.** ch-oracles owns the `agent:lint:<lang>`,
   `agent:doc-drift`, `agent:coverage`, `agent:dep-drift`,
   `agent:auto-merge`, `agent:autofix`, `agent:conflict`,
   `agent:worker-tuning` labels. spectacles owns its `sdd:*` namespace.
   The `needs-human` label is shared (cross-suite hand-off; honored by
   both, owned by spectacles when both are installed).
3. **AGENTS.md section ownership.** `.github/AGENTS.md` carries
   suite-specific marker sections:
   - `<!-- ch-oracles:build-commands:begin -->` / `<!-- ch-oracles:build-commands:end -->`
   - `<!-- spectacles:pipeline:begin -->` / `<!-- spectacles:pipeline:end -->`

   `quick-setup.sh` for each suite inserts or updates only its own section
   and leaves the other untouched.
4. **`labels.yml` merge.** `quick-setup.sh` appends ch-oracles labels to
   an existing `.github/labels.yml` rather than overwriting it. A label
   already present (same name) is left as-is — color and description from
   the prior install win.

## gh-aw pin drift

ch-oracles and spectacles compile their workflows with their own pinned
gh-aw versions. Each suite's lock file is self-contained
(`inlined-imports: true`) and consumer wrappers reference them via `uses:`
from the upstream repos. Two suites pinning different gh-aw versions is
supported as long as both versions produce lock files that GitHub Actions
can run (the lock-file format is currently stable across v0.6x–v0.7x of
gh-aw).

When a major gh-aw release breaks lock-file compatibility, each suite must
update independently. Consumers may need to bump both suite tags in
lockstep; this is documented in each suite's release notes.

## Consequences

- A consumer can run `scripts/quick-setup.sh --suite oracles` after
  spectacles is already installed, and vice versa.
- An operator who removes one suite leaves the other's wrappers and
  AGENTS.md sections untouched.
- The `needs-human` label semantics are coordinated: both suites' workers
  decline to act on items carrying it. ch-oracles never owns the label
  (does not introduce it if absent), but honors it always.
