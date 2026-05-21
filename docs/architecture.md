# Architecture

ch-oracles workflows follow a consistent loop: a chore detects something,
files an issue with a typed label, a worker picks the issue up and opens
a PR, and the consumer's existing CI gates the merge.

## The chore → issue → worker → PR loop

```mermaid
flowchart LR
    A[chore<br/>audit run] -->|finds drift| B[files issue<br/>agent:* label]
    B -->|reactive trigger| C[worker-fix<br/>picks one issue]
    C -->|opens| D[PR<br/>:worker:label:]
    D -->|review comments| E[worker-iterate<br/>pushes commits]
    E --> D
    D -->|consumer CI passes| F((merged))
    D -->|merge conflict| G[pr-conflict-resolver<br/>rebases or escalates]
    G -->|conflict resolved| D
    G -->|non-trivial| H[needs-human<br/>one-way off-switch]

    classDef accent fill:#f5e9ff,stroke:#6b21a8,stroke-width:2px;
    class F accent;
```

Every safe output (issue, PR, comment, label) is capped by gh-aw's
safe-output runtime — never raw GitHub API calls from the agent.

## Distribution model

```mermaid
flowchart TB
    subgraph SOT["gominimal/ch-oracles (source of truth)"]
        S1[workflows/&lt;chore&gt;.md<br/>source]
        S2[shared/*.md<br/>fragments]
        S3[wrappers/&lt;chore&gt;.yml<br/>thin caller]
        S1 -->|gh aw compile<br/>inlined-imports| LK[.github/workflows/<br/>&lt;chore&gt;.lock.yml]
        S2 -.imported.-> LK
    end

    subgraph CR["consumer repo"]
        W[.github/workflows/<br/>&lt;chore&gt;.yml]
        W -->|uses:| LK
    end

    S3 -.installs as.-> W

    classDef accent fill:#f5e9ff,stroke:#6b21a8,stroke-width:2px;
    class LK accent;
```

ch-oracles hosts the heavy `.lock.yml` files. Consumers install only the
thin `.yml` wrappers via `quick-setup.sh`. Upgrades pull a newer release
tag.

## Compile-time vs runtime

- **Compile-time:** `gh aw compile workflows/*.md` inlines every imported
  fragment (`shared/*.md`) and produces a self-contained
  `.github/workflows/<name>.lock.yml`. Network egress allowlists,
  safe-output caps, and tool allowlists are baked into the lock at compile
  time.
- **Runtime:** wrappers in consumer repos invoke
  `uses: gominimal/ch-oracles/.github/workflows/<name>.lock.yml@<ref>`.
  The lock file's pre-activation guards (role check, label-namespace gate)
  evaluate the consumer's event context. The agent step runs in a sandbox
  with the baked allowlists.

## Safe-outputs gate

```mermaid
flowchart LR
    agent[agent emits<br/>JSON output] --> validate{gh-aw runtime}
    validate -->|cap exceeded| reject[reject<br/>log noop]
    validate -->|HTML tag<br/>not allowed| strip[strip tag]
    validate -->|finding-id<br/>match exists| update[update-issue]
    validate -->|new finding| create[create-issue]
    strip --> emit[GitHub API]
    update --> emit
    create --> emit

    classDef accent fill:#f5e9ff,stroke:#6b21a8,stroke-width:2px;
    class validate accent;
```

The agent never invokes the GitHub API directly. Every chore that writes
an issue, PR, comment, or label goes through the safe-output gate.

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

`worker-fix.md` reads the candidate issue's `agent:*` label and routes to
a language-aware fix path:

```mermaid
flowchart TD
    I[issue with agent:* label] --> S{label?}
    S -->|agent:lint:rust| R[apply cargo fmt + clippy --fix<br/>verify per rust-build-commands]
    S -->|agent:lint:python| P[apply ruff format + check --fix<br/>verify per python-build-commands]
    S -->|agent:lint:go| G[apply gofmt + goimports<br/>verify per go-build-commands]
    S -->|agent:lint:toml| T[apply taplo fmt<br/>verify per toml-build-commands]
    S -->|agent:lint:ncl| N[apply nickel format<br/>verify per nickel-build-commands]
    S -->|agent:doc-drift| D[edit doc to match source]
    S -->|agent:coverage| V[add tests per issue]
    S -->|agent:dep-drift| U[apply upgrade command]
    R --> O[open PR]
    P --> O
    G --> O
    T --> O
    N --> O
    D --> O
    V --> O
    U --> O

    classDef accent fill:#f5e9ff,stroke:#6b21a8,stroke-width:2px;
    class O accent;
```

Verification commands per language come from
[`shared/build-matrix.md`](https://github.com/gominimal/ch-oracles/blob/main/shared/build-matrix.md),
with consumer `AGENTS.md` overrides taking precedence.

## pr-conflict-resolver detect job

```mermaid
sequenceDiagram
    participant trigger as push/cron/PR sync
    participant detect as detect job
    participant agent as agent job (Copilot)
    participant gh as GitHub API

    trigger->>detect: invoke
    detect->>gh: pulls.list (open)
    detect->>gh: pulls.get per PR (mergeable?)
    alt no conflicting worker PR
        detect-->>trigger: has_work=false<br/>skip agent
    else conflict found
        detect-->>agent: has_work=true
        agent->>gh: rebase + push or apply needs-human
    end
```

The cheap non-LLM `detect` job scans for open worker PRs with
`mergeable: false`. The expensive agent job only fires when actual work
exists; on a quiet repo, scheduled ticks cost ~one API page and zero
model tokens.

## needs-human as a one-way off-switch

When the conflict resolver hits a non-trivial merge conflict, it applies
the `needs-human` label and stops. Both ch-oracles and (when co-installed)
spectacles workers honor `needs-human` as a one-way off-switch: a labeled
item is off-limits to every chore until a human removes the label.

This makes `needs-human` the canonical cross-suite "stop" signal in a
co-installed repo.
