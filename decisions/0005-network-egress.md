# 0005 — Per-workflow network egress; polyglot worker union accepted

Status: Accepted
Date: 2026-05-19

## Context

gh-aw lock files declare a `network.allowed:` block listing ecosystem ids
(`defaults`, `rust`, `python`, `go`, `nickel`) that compose into the
runtime egress allowlist. Two policies were considered:

1. **One shared `network-egress.md` fragment** imported by every workflow.
   Every chore receives the union of all 5 languages' allowlists.
2. **Per-workflow declaration.** Each chore's frontmatter declares only
   the languages it actually needs (`[defaults, rust]` for the Rust lint
   chore).

## Decision

**Per-workflow declaration.** Each chore-* and trivial-dep-bump-* workflow
declares only its own language's ecosystem id. The polyglot workers
(`worker-fix`, `worker-iterate`, `pr-conflict-resolver`) declare the union
explicitly: `[defaults, rust, python, go, nickel]`.

A single `shared/network-egress.md` fragment exists as documentation only,
not as a compile-time import. It describes the per-language allowlist
convention.

## Rationale

- **Audit trail clarity.** A reader inspecting `chore-style-rust.lock.yml`
  sees `network.allowed: [defaults, rust]` and understands the security
  boundary at a glance. A unioned fragment would obscure this.
- **Least-privilege at the lock level.** Each chore's network surface is
  exactly what it needs. A compromised model output for the Python lint
  chore cannot reach crates.io, even if the prompt is manipulated.
- **Polyglot worker is the exception, not the rule.** Workers must verify
  any candidate issue's language; their attack surface is wider by
  design. The runtime bash-command allowlist (constrained per resolved
  language via `vars.CH_ORACLES_LANGUAGE`; see ADR 0004) narrows the
  practical surface.

## Consequences

- The 5 chore-style workflows each declare a single-language allowlist.
- The 3 trivial-dep-bump workflows each declare a single-language allowlist.
- The 3 audit workflows (docs-patrol, test-coverage-detector,
  dependency-review) declare polyglot-aware allowlists because they
  inspect manifests across languages.
- The 3 worker workflows declare the full union.
- A consumer can audit network egress per-chore by reading the lock file's
  `network.allowed` block; no fragment chase required.
