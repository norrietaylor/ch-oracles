# Architecture

ch-oracles workflows follow a consistent loop:

```text
chore (audit) ─► files issue (agent:*)
                       │
                       ▼
              worker-fix picks issue ─► opens PR
                                          │
                                          ▼
                                 reviewer comments
                                          │
                                          ▼
                              worker-iterate pushes commits
                                          │
                                          ▼
                              CI passes ─► auto-merge or human-merge
```

## Distribution model

```text
norrietaylor/ch-oracles                          consumer repo
─────────────────────────                        ─────────────
workflows/<chore>.md  ──compile──►  .github/workflows/<chore>.lock.yml
                                                  │
                                                  │ uses:
                                                  ▼
                                   .github/workflows/<chore>.yml (wrapper, installed by quick-setup.sh)
```

ch-oracles hosts the heavy `.lock.yml` files. Consumers install only the
thin `.yml` wrappers via `quick-setup.sh`. Upgrades pull a newer release
tag.

## Compile-time vs runtime

- **Compile-time:** `gh aw compile workflows/*.md` inlines every imported
  fragment (`shared/*.md`) and produces a self-contained
  `.github/workflows/<name>.lock.yml`. Network egress allowlists, safe-output
  caps, and tool allowlists are baked into the lock at compile time.
- **Runtime:** wrappers in consumer repos invoke `uses:
  norrietaylor/ch-oracles/.github/workflows/<name>.lock.yml@<ref>`. The
  lock file's pre-activation guards (role check, label namespace gate)
  evaluate the consumer's event context. The agent step runs in a sandbox
  with the baked allowlists.

## Safe-outputs

Every chore that writes (issue, PR, comment, label) goes through gh-aw's
safe-output gate:

```yaml
safe-outputs:
  create-issue:
    max: 1
    labels: [agent:doc-drift]
  update-issue:
    max: 1
  create-pull-request:
    max: 1
    draft: ${{ false }}
    auto-merge: true
```

The agent emits a structured JSON output; gh-aw's runtime validates it
against the safe-output schema, applies caps, strips HTML outside the
allowlist, and performs the GitHub API call. The agent never invokes the
API directly.

See [`shared/safe-output-create-issue.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/safe-output-create-issue.md)
for the dedup contract and HTML allowlist.

## Per-finding dedup

A chore's issue body always starts with:

```html
<!-- finding-id: <chore>::<lang>::<identity> -->
```

Before emitting `create-issue`, the agent searches for an existing open
issue with a matching marker; if found, it emits `update-issue` instead.
This prevents duplicate filings across scheduled runs and across reruns
after `workflow_dispatch`.

## Worker switch table

`worker-fix.md` reads the candidate issue's `agent:*` label and routes to a
language-aware fix path. The switch table is in
[`workflows/worker-fix.md`](https://github.com/norrietaylor/ch-oracles/blob/main/workflows/worker-fix.md).

Verification commands per language come from
[`shared/build-matrix.md`](https://github.com/norrietaylor/ch-oracles/blob/main/shared/build-matrix.md),
with consumer `AGENTS.md` overrides taking precedence.

## pr-conflict-resolver detect job

The wrapper for `pr-conflict-resolver` includes a cheap non-LLM `detect`
job that scans open worker PRs for `mergeable: false`. The expensive
agent job only fires when actual work exists; on a quiet repo, scheduled
ticks cost ~one API page and zero model tokens.

See [ADR 0004 in spectacles](https://github.com/norrietaylor/spectacles/blob/main/decisions/0001-needs-human.md)
for the rationale behind the `needs-human` label as a one-way off-switch.
