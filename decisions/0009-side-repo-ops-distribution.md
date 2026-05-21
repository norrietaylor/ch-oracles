# 0009 — Side-repo-ops distribution; consumer repos receive issues, not workflows

Status: Accepted
Date: 2026-05-21

## Context

ADR 0006 (`0006-engine-split.md`) and ADR 0007 (`0007-fragment-sync-policy.md`)
codified the prior distribution model: ch-oracles ships `.md` sources and
shared fragments; consumer repos install thin wrappers via a setup script,
and each consumer repo runs the compiled `workflow_call` lock files in its
own runner against its own checkout. Wrappers are renewed by bumping a
`@<ref>` pin.

Two operational pressures made this model expensive at the scale we want
to support:

1. **Per-target install burden.** Onboarding a new consumer repo requires
   running `quick-setup.sh`, opening a PR, reviewing wrappers, merging,
   and confirming labels — for every chore × every language × every repo.
   The blast radius of a wrapper change is the cross product.
2. **Drift between authoring and execution.** Workflow improvements land
   in ch-oracles, but the runtime version on a given consumer is whatever
   `@<ref>` its wrappers pin. A consumer that has not refreshed wrappers
   is running stale prompts against fresh code.

`github/gh-aw` documents a complementary model under
`docs/src/content/docs/patterns/side-repo-ops.mdx`: a *side repository*
hosts the workflows, schedules + dispatches them on its own runners, and
writes outputs into target repositories via `safe-outputs.target-repo:`
plus a cross-repo credential. The target repo installs nothing.

We adopt that model for the next generation of chores (the 20 ports
catalogued in `99-ADOPTION-PLAN-ch-oracles.md`).

## Decision

The chore suite has three roles:

| Role | Repo | Responsibility |
|---|---|---|
| Source-of-record | `norrietaylor/ch-oracles` | Canonical `.md` workflow sources, shared fragments, ADRs, planning docs. Owns the conventions. |
| Operator (side-repo) | `gominimal/min-aw` | Vendors the `.md` sources (bootstrap-fork per ADR 0007), compiles them with `gh aw compile`, hosts the compiled `.lock.yml`, runs the workflows on its own runners on schedule + `workflow_dispatch`. Holds the cross-repo credential. |
| Consumer | `gominimal/minimal` (and others) | Receives issues / PRs / comments via `safe-outputs.target-repo:`. Installs nothing. May own optional relay workflows for slash-command-style triggers when polling is unsuitable. |

Concretely:

- Workflows authored in ch-oracles are scaffolded with a `workflow_call`
  interface accepting `target-repo` (string) and `target-ref` (string,
  default `main`) inputs, plus `mode: report|autofix` per ADR 0002.
- The operator fork in min-aw adds schedule + dispatch triggers, binds
  `target-repo` to the intended consumer, declares the cross-repo
  credential in `safe-outputs.github-app`, `tools.github.github-app`,
  and `checkout.github-app`, and lists the target repo in the App's
  `repositories:` array.
- Cross-repo writes use the existing `gominimal-aw-bot` GitHub App
  (`min-aw` ADR 0002). Each consumer installs the App with the
  permissions enumerated below; no per-consumer PAT.
- Consumer repos receive issues with the `<!-- finding-id: ... -->`
  marker in the body for cross-repo dedup. The marker survives runner
  restarts and works regardless of which side-repo instance posted it.

## App permissions on the consumer

The `gominimal-aw-bot` installation on each consumer carries:

| Permission | Access | Used for |
|---|---|---|
| Contents | Read | Checkout target source for local detector runs |
| Issues | Read + Write | Comment, label, file findings |
| Pull requests | Read + Write | Open / update advisory PRs |
| Metadata | Read | Baseline |

Write permissions are scoped to the issue / PR safe-output handlers; the
agent itself runs without write capabilities. Per ADR 0001 the outputs
are advisory only; the App never gates a merge.

## Consequences

Upside:

- **Onboarding is one-time per consumer**: install the App, add the
  `agent:*` labels, optionally seed `.github/AGENTS.md`. No wrapper PRs,
  no scheduled refresh cadence.
- **Prompt updates ship instantly**: bumping the source in ch-oracles and
  re-compiling in min-aw is the entire deployment. No consumer-side PR.
- **Smaller surface in the consumer repo**: no `.github/workflows/`
  files, no `wrappers/` directory, no embedded `gh-aw` lock files.
- **Audit lives in one place**: every chore run is in min-aw's Actions
  history, regardless of how many consumers it targeted.
- **Multi-target dispatch is mechanical**: a parametric wrapper or a
  matrix in min-aw lets one chore cover N consumers without N×M file
  fan-out in the consumer org.

Downside:

- **Side-repo events are isolated**: a consumer-repo event
  (`issues.labeled`, `pull_request.opened`) cannot trigger a side-repo
  workflow directly. PR-event-driven chores (`pr-quality-reviewer`,
  some failure investigators) need either scheduled polling or a thin
  relay workflow installed in the consumer. The relay is one `.yml`
  file with a `safe-outputs.workflow-dispatch:` block — much smaller
  than the full chore install — but it is not zero.
- **Credential blast radius**: the App carries write on every installed
  consumer. Compromise of the App private key (`APP_PRIVATE_KEY`) gives
  write access across the org's installed consumers. The mitigation is
  that the secret lives in one repo (min-aw); per ADR 0002 minting is
  per-job and tokens expire in one hour. Rotation is centralised.
- **Polyglot detection runs against the checked-out target, not the
  caller**: the `build-matrix.md` manifest-sniff must run after the
  side-repo checks out the consumer. Workflows declare a `checkout:`
  block with `path: target` and `current: true`; the agent prompt is
  required to `cd target` before running any detector. ADR 0004
  (polyglot worker invariants) is unchanged in spirit, but the
  implementation lives in min-aw not the consumer.
- **`quick-setup.sh` shrinks**: the installer no longer ships wrappers
  for chores that adopt this model. It retains a role for label seeding
  (`.github/labels.yml` sync) and, when needed, relay-workflow install.
  Existing wrappers (worker-fix, chore-style-*, etc.) continue under
  the prior model until they are migrated; this ADR governs new
  chores only, not retroactive migration.

## Naming

Operator workflows in min-aw take the same chore name as the ch-oracles
source. The cross-repo dispatch is captured in the `target-repo` input
default, not in the filename. A single chore targeting multiple
consumers uses one of:

- Multiple operator wrappers, one per target (e.g.
  `chore-deadcode-rust-minimal.yml`, `chore-deadcode-rust-spectacles.yml`).
- A single parametric wrapper that accepts `target-repo` and is
  invoked once per target via a matrix.

We default to the per-target file when the count is low (≤3) and switch
to the matrix when the count grows.

## Label namespace

The `agent:*` label namespace declared in
`templates/.github/labels.yml` continues to apply, but the collision
surface moves from filename to label: issues authored by a side-repo
chore land in the consumer repo with `agent:<class>:<lang>` labels.
ADR 0003 (spectacles coexistence) governs only the label namespace
under this model; filename collisions are no longer possible.

## References

- ADR [`0001-not-gating.md`](0001-not-gating.md) — outputs are advisory.
- ADR [`0002-style-mode-flag.md`](0002-style-mode-flag.md) — `mode` input.
- ADR [`0003-spectacles-coexistence.md`](0003-spectacles-coexistence.md) — label namespace boundary.
- ADR [`0007-fragment-sync-policy.md`](0007-fragment-sync-policy.md) — fork-on-bootstrap header.
- min-aw ADR `0002-github-app-not-pats.md` — the App credential strategy.
- [`gh-aw` side-repo-ops pattern](https://github.github.com/gh-aw/patterns/side-repo-ops/) — the canonical reference.
- `99-ADOPTION-PLAN-ch-oracles.md` — the 20 chores adopted under this model.
