# 0007 — `principles.md` and `rigor.md` are forks of spectacles; no auto-sync

Status: Accepted
Date: 2026-05-19

## Context

`shared/principles.md` and `shared/rigor.md` describe foundational agent
behavior (think before acting, simplicity first, evidence standards,
confidence thresholds). Both files were authored for
[gominimal/spectacles](https://github.com/gominimal/spectacles)
and are equally applicable to ch-oracles.

Three approaches were considered:

1. **gh-aw import at compile time.** Workflows import
   `gominimal/spectacles/shared/principles.md@<ref>` directly.
2. **Verbatim fork at bootstrap.** Copy the file content once into
   `shared/principles.md` in ch-oracles; no automated sync.
3. **Periodic re-fork via CI.** A scheduled job pulls the latest from
   spectacles and opens a PR to update ch-oracles' copies.

## Decision

**Verbatim fork at bootstrap.** ch-oracles owns
`shared/principles.md` and `shared/rigor.md` as static, content-equivalent
copies of the spectacles versions captured at bootstrap. Each file carries
a header comment recording the source SHA and date:

```html
<!-- Source: gominimal/spectacles/shared/<file>@<sha> at bootstrap (YYYY-MM-DD). Not auto-synced. -->
```

No automated sync. Drift between the two suites is allowed.

## Rationale

- **Behavioral stability.** A change to spectacles' principles should not
  silently change ch-oracles' agent behavior on the next scheduled run.
  Each suite's behavior is anchored to its own pinned shared fragments.
- **Avoids cross-repo coupling.** A gh-aw compile-time import from
  spectacles would couple ch-oracles' release process to spectacles'
  ref stability. If spectacles deletes or renames a fragment, every
  ch-oracles lock file fails to recompile.
- **Drift is acceptable for foundational text.** principles.md and
  rigor.md describe stable, slow-moving behavioral norms. The cost of
  occasional manual reconciliation is low compared to the coupling risk.

## When to revisit

If a divergence between the two files becomes problematic (e.g.,
spectacles introduces a third principle that ch-oracles agents should
honor), an operator manually copies the updated content from
spectacles, updates the source header to record the new SHA and date,
and commits. The two files do not need to remain bit-identical, only
behaviorally consistent.

Consider revisiting this ADR if:

- The fragments diverge significantly and the divergence causes confusion.
- A third sibling suite is added that would benefit from a shared source.
- gh-aw introduces a stable cross-repo import mechanism that resolves the
  coupling concerns.
