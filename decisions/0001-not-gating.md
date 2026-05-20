# 0001 — ch-oracles is not a merge gate

Status: Accepted
Date: 2026-05-19

## Context

ch-oracles chores file issues and open PRs. The temptation is to wire them
into branch protection — "the dependency-review chore found a critical CVE,
why didn't the merge block?" — but the chores' reliability profile is
materially different from consumer CI.

## Decision

**ch-oracles outputs are advisory, never gating.** No `chore-style-*`,
`docs-patrol`, `test-coverage-detector`, `dependency-review`, or worker
output appears in `required_status_checks`. Branch protection on a consumer
repo depends only on the consumer's existing CI.

## Rationale

- **Reliability asymmetry.** Consumer CI is local, deterministic, and
  trusted. ch-oracles depends on external LLM APIs (Copilot, Claude) with
  variable latency and occasional service degradation. A required gate on
  ch-oracles output couples merge availability to upstream model
  availability.
- **Blast radius.** Safe-output gates (caps, dedup, HTML allowlist) protect
  the consumer from runaway agent output for writes. Making a gate would
  invert the protection: a confused agent could permanently block merges
  until an operator intervenes.
- **Reversibility.** A future ch-oracles version could elect to gate
  specific chores per consumer if reliability proves consistent over a long
  window. The default position is non-gating; opt-in gating is a
  per-consumer decision, not a default behavior.

## Verification

A weekly chore (not yet shipped; tracked as a future addition) audits
branch protection on consumer repos and surfaces any unexpected
ch-oracles-prefixed required check as an issue in the source-of-truth repo.

## Consequences

- Chore failures file issues or open PRs but never block merges.
- Auto-merge chores (`trivial-dep-bump-*`) rely on the consumer's CI as
  the sole gate. If CI passes, the PR auto-merges; if it fails, the PR
  sits open with the failure visible.
- A consumer that wants stricter behavior can opt-in by adding individual
  chore status checks to their own branch-protection ruleset. That is a
  consumer-side choice, not a ch-oracles default.
