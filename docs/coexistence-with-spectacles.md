# Coexistence with spectacles

[norrietaylor/spectacles](https://github.com/norrietaylor/spectacles) is the
spec-driven-development pipeline suite (sdd-spec → sdd-triage → sdd-execute
→ sdd-validate → sdd-review). ch-oracles is the chore suite. Both can be
installed in the same consumer repo without collision.

See [ADR 0003](https://github.com/norrietaylor/ch-oracles/blob/main/decisions/0003-spectacles-coexistence.md)
for the full contract.

## Filename namespaces

| Suite | Wrapper file prefix |
|---|---|
| spectacles | `sdd-*.yml`, `distillery-sync.yml` |
| ch-oracles | `chore-style-*.yml`, `docs-patrol.yml`, `test-coverage-detector.yml`, `dependency-review.yml`, `trivial-dep-bump-*.yml`, `worker-fix.yml`, `worker-iterate.yml`, `pr-conflict-resolver.yml` |

No collisions.

## Label namespaces

| Suite | Owned labels |
|---|---|
| spectacles | `sdd:*` |
| ch-oracles | `agent:lint:<lang>`, `agent:doc-drift`, `agent:coverage`, `agent:dep-drift`, `agent:auto-merge`, `agent:autofix`, `agent:conflict`, `agent:worker-tuning` |
| **shared** | `needs-human` (cross-suite hand-off; honored by both, owned by spectacles when co-installed) |

`quick-setup.sh` for each suite appends labels to an existing
`labels.yml`; labels already present (same name) are left alone.

## AGENTS.md ownership

`.github/AGENTS.md` carries suite-specific marker sections:

```markdown
<!-- spectacles:pipeline:begin -->
...spectacles content...
<!-- spectacles:pipeline:end -->

<!-- ch-oracles:build-commands:begin -->
...ch-oracles content...
<!-- ch-oracles:build-commands:end -->
```

Each suite's `quick-setup.sh` updates only its own section and leaves the
other untouched. An operator can edit either section's content; subsequent
`--update` runs preserve those edits (only the boilerplate between markers
is refreshed).

## Install order

Order does not matter. Install whichever you start with first; install the
other later with the same script invocation. Each install is additive.

```bash
# Either order works
curl -fsSL .../spectacles.../quick-setup.sh   | bash -s -- --suite sdd
curl -fsSL .../ch-oracles.../quick-setup.sh   | bash -s -- --suite oracles
```

## gh-aw version drift

The two suites pin their own gh-aw versions in their respective lock
files. Co-install is supported across gh-aw versions that share a
compatible lock-file schema (currently v0.6x and v0.7x).

When gh-aw introduces a breaking lock-file change, both suites must update
independently. Each suite's release notes will call out the affected
version range.

## Cross-suite hand-off via `needs-human`

When a ch-oracles worker hits a conflict it cannot resolve, it applies the
`needs-human` label and stops. spectacles' agents also honor that label
(per spectacles' [ADR 0001](https://github.com/norrietaylor/spectacles/blob/main/decisions/0001-needs-human.md)).
A human clearing the label resumes both suites' agents on that item.

This makes `needs-human` the canonical cross-suite "stop" signal in a
co-installed repo.
