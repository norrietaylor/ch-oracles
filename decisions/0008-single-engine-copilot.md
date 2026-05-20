# 0008 — Workers migrate to Copilot engine; suite is single-engine

Status: Accepted
Date: 2026-05-20

## Context

[ADR 0006](0006-engine-split.md) split the suite across two inference
backends: chores ran on `engine: copilot` (backed by `COPILOT_GITHUB_TOKEN`)
and workers ran on `engine: claude` (backed by `ANTHROPIC_API_KEY`). The
rationale was that workers do multi-step refactors with verification loops
and benefit from peak reasoning, while chores do narrow pattern-matching at
lower cost. Consumer repos had to provision two secrets and two billing
relationships.

Operational discovery during the ch-oracles end-to-end run against
`gominimal/spectacles-test` revealed the cross-provider failure mode this
arrangement embeds: when the Anthropic credit balance was exhausted,
worker stages F, G, and H all failed with
`billing_error: "Credit balance is too low"` while the Copilot-backed chore
stages D and E ran clean. A single billing outage on one provider took out
exactly half the suite — the half that does the most consequential writes
(PR creation, rebase, follow-up commits).

The reasoning quality gap that motivated ADR 0006 has narrowed in practice.
The worker prompts are tightly scoped by the switch table in
`worker-fix.md`, by the verification gate, and by `safe-outputs` caps; the
multi-step branching they do is constrained enough that Copilot completes
it without observed quality degradation in the chore tier or in the
spectacles co-installation.

## Decision

Migrate all three worker workflows to `engine: copilot`:

- `workflows/worker-fix.md`
- `workflows/worker-iterate.md`
- `workflows/pr-conflict-resolver.md`

Drop `ANTHROPIC_API_KEY` from every wrapper, lock file, installer prompt,
and documentation surface. The suite now requires exactly one inference
secret: `COPILOT_GITHUB_TOKEN`.

ADR 0006 is **superseded by this ADR**.

## Rationale

- **Single billing surface.** One provider, one credit balance, one
  outage radius. A consumer that gets the suite running on Copilot has the
  entire suite running.
- **Removed cross-provider failure mode.** No combination of provider
  status pages now produces the "half the suite is dark" state observed
  in the E2E run.
- **Simpler operator setup.** `quick-setup.sh`'s post-install message
  drops from three required secrets to two (`APP_PRIVATE_KEY` plus
  `COPILOT_GITHUB_TOKEN`). Documentation, ADRs, and consumer wrappers
  collapse to a single mental model.
- **Fewer secrets to provision and rotate.** Each secret added to a
  consumer repo is a small operational tax: store, share, rotate, audit.
  Removing one across every consumer compounds.
- **No observed behavior degradation.** Worker prompts are constrained by
  the switch table, the verification gate, the rigor checklist, and
  safe-outputs caps. The peak-reasoning argument from ADR 0006 was
  defensible in the abstract but did not survive contact with the actual
  worker workload, which is more "follow the recipe" than "open-ended
  multi-step planning."

## Consequences

- Consumer repos installed before this ADR must remove the
  `ANTHROPIC_API_KEY` secret on next upgrade. The secret being present
  causes no harm; it simply becomes unused.
- The "expensive thinking, cheap pattern matching" framing in ADR 0006 is
  retired. If a future workload genuinely needs a different engine,
  per-workflow `engine:` overrides remain available — the suite picks
  Copilot as the default rather than as a tier-specific choice.
- The reasoning-tier argument from ADR 0006 could in principle motivate a
  future revision (e.g., a `worker-architect` workflow that does deep
  planning). The bar is: observed worker output is consistently failing
  on a class of issue that better reasoning would solve. That bar is not
  met today.

## When to revisit

Consider revisiting this ADR if:

- Copilot's per-call ergonomics or rate limits start to bite a specific
  worker workflow's behavior in a way that's traceable to engine choice
  rather than prompt scoping.
- A new worker tier is added whose task class is genuinely outside the
  switch-table-bounded shape of the current workers.
- A cross-provider fallback strategy becomes cheap to implement at the
  gh-aw layer (today it is not, and a manual fallback would re-introduce
  the cross-provider failure mode this ADR removed).
