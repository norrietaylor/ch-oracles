## Safe-output guardrails: create / update issue

Apply the following caps when using the `create-issue` and `update-issue`
safe outputs:

- **max: 1** — Open at most one issue per workflow run unless the chore
  overrides it. If a matching open issue already exists for the same finding
  identity, emit `update-issue` against it instead of `create-issue`.
- **max-mentions: 10** — Include at most 10 `@`-mentions across the issue
  title and body combined.
- **max-links: 50** — Include at most 50 hyperlinks in the issue body.
- **No `close-older-issues`.** Do not set this to `true`. The gh-aw runtime
  keys close-older only on the workflow-id marker, not on per-finding
  identity; enabling it causes cross-finding cascades where two distinct
  findings from the same chore mutually close each other. Per-finding dedup
  is implemented agent-side via the idempotency contract below. This applies
  to `close-older-key` as well: a per-workflow static value cannot replace
  per-finding dedup.

### HTML tag allowlist

Only the following HTML tags are permitted in issue bodies:

```text
<details>, <summary>, <code>, <pre>, <br>, <ul>, <ol>, <li>,
<strong>, <em>, <b>, <i>
```

Strip all other HTML tags before emitting the issue body.

### Idempotency contract (per-finding dedup)

Every chore-emitted issue body MUST include a structured finding-identity
marker as the FIRST line of the body, on its own line:

```html
<!-- finding-id: <chore>::<lang>::<identity> -->
```

- `<chore>` — the chore name (e.g., `lint`, `tidy`, `doc-drift`, `coverage`,
  `dep-drift`).
- `<lang>` — the language scope (`rust`, `python`, `go`, `toml`, `ncl`), or
  `n-a` if not applicable (e.g., `doc-drift::n-a::README.md::link-404`).
- `<identity>` — the per-chore identity field defined in each chore's
  Reporting section (e.g., `src/lib.rs::42::E0599` for clippy, `tokio::CVE-2024-0001`
  for dep-drift).

The marker is normalized lowercase, alphanumeric plus `,:_/.-`.

Before emitting any safe-output, run this dedup procedure:

1. Search open issues with the chore's `agent:*` label and a body containing
   `<!-- finding-id: <chore>::<lang>::<identity> -->` for the current
   finding's identity:

   ```bash
   gh issue list --search "in:body \"finding-id: <chore>::<lang>::<identity>\""
   ```

2. **If a matching open issue exists**: emit `update-issue` with the
   matched `issue_number=<n>` and `operation=replace`, posting the fresh
   body. The `issue_number` parameter is **required** and MUST be the number
   returned by step 1's search — the audit chores run on `schedule` and
   `workflow_dispatch`, so the safe-output runtime is not in an issue-event
   context and will reject any `update_issue` call that omits an explicit
   `issue_number`. Do not call `create-issue`. Do not call
   `close-older-issues`-style closures; mutating fixes should land via the
   worker chore, not this audit.
3. **If no matching open issue exists**: emit `create-issue` with the marker
   as the first body line.

This contract is the only source of dedup. The runtime no longer auto-closes
prior issues, so an obsolete issue (drift that has been fixed) stays open
until either an operator closes it or a future janitor chore reaps stale
entries. The trade is intentional: false-cascades are far more harmful than
slightly-stale-open entries an operator can close.

### Severity labeling

Attach exactly one severity label from the set declared in this repo's
`labels.yml`. Do not create new labels at runtime.
