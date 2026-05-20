# 0004 — Polyglot worker language detection

Status: Accepted
Date: 2026-05-19

## Context

`worker-fix`, `worker-iterate`, and `pr-conflict-resolver` must build and
verify code in any of five languages (rust, python, go, toml, ncl). The
worker needs to pick the right build/test/lint commands per run.

Three resolution strategies were considered:

1. **One worker per language** — `worker-fix-rust`, `worker-fix-python`,
   etc.
2. **Single polyglot worker that detects per-run.**
3. **Per-repo language declaration via repository variable.**

## Decision

Single polyglot worker with this resolution order:

1. **`vars.CH_ORACLES_LANGUAGE` repository variable.** If set, the worker
   restricts its bash command invocation to that language's toolchain.
   Valid: `rust | python | go | toml | ncl | polyglot`.
2. **`AGENTS.md` `## Build Commands (ch-oracles override)` section.**
   Honored if `vars.CH_ORACLES_LANGUAGE` is unset.
3. **Manifest sniff at runtime.** `Cargo.toml`→rust, `pyproject.toml`→
   python, `go.mod`→go, presence of `*.toml`→toml, presence of `*.ncl`→
   ncl. Multiple matches → polyglot.
4. **Candidate-issue label suffix.** For polyglot repos, the worker
   prefers the language matching the candidate issue's `agent:lint:<lang>`
   label suffix.

## Rationale

- **Single workflow simplifies install.** Per-language workers would
  require 3 × 5 = 15 worker wrappers and a switch-table per consumer for
  routing candidate issues to the right worker.
- **Per-run resolution is cheap.** Language detection is ~3 file
  existence checks; the runtime cost is negligible compared to model
  inference.
- **Network egress widens, but the runtime gate narrows it.** The lock
  file declares the union of every supported ecosystem
  (`[defaults, rust, python, go, nickel]`) because GitHub Actions
  resolves network allowlists at compile time. The worker's bash command
  allowlist is constrained at runtime via the resolved language: a
  Python-only repo running this worker only ever invokes `uv`/`ruff`/
  `mypy`/`pytest`, never `cargo` or `go`. See ADR 0005.

## Consequences

- A consumer with mixed-language repos uses one worker install. The
  worker's per-run resolution handles routing.
- A consumer with a single-language repo can pin
  `vars.CH_ORACLES_LANGUAGE` to that language for clarity; this also
  documents intent.
- Future language additions (Zig, Ruby) require updating the manifest
  sniff and adding language fragments; no worker-wrapper changes are
  needed.
