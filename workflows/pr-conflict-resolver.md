---
# Distributed as a reusable workflow per the gh-aw sharing pattern.
# Consumer-side triggers (push to main + scheduled backstop + reactive
# pull_request:synchronize) live in `wrappers/pr-conflict-resolver.yml`.
on:
  workflow_call:
    secrets:
      APP_PRIVATE_KEY:
        description: "Private key for the ch-oracles bot GitHub App."
        required: true
      ANTHROPIC_API_KEY:
        description: "API key for engine: claude inference calls."
        required: true
  roles: all

permissions:
  contents: read
  issues: read
  pull-requests: read

engine: claude
inlined-imports: true
strict: false

network:
  allowed: [defaults, rust, python, go, nickel]

env:
  RESOLVER_BRANCH_PREFIX: 'conflict-resolver/'

imports:
  - norrietaylor/ch-oracles/shared/principles.md@main
  - norrietaylor/ch-oracles/shared/rigor.md@main
  - norrietaylor/ch-oracles/shared/repo-conventions.md@main
  - norrietaylor/ch-oracles/shared/safe-output-create-issue.md@main
  - norrietaylor/ch-oracles/shared/runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/rust-build-commands.md@main
  - norrietaylor/ch-oracles/shared/python-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/python-build-commands.md@main
  - norrietaylor/ch-oracles/shared/go-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/go-build-commands.md@main
  - norrietaylor/ch-oracles/shared/build-matrix.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  push-to-pull-request-branch:
    max: 1
  add-comment:
    max: 1
    discussions: false
    pull-requests: true
    issues: false
  add-labels:
    max: 1
    allowed:
      - needs-human
      - agent:conflict
  noop:
    max: 1
    report-as-issue: false

tools:
  github:
    allowed:
      - list_pull_requests
      - get_pull_request
      - pull_request_read
      - create_issue_comment
  bash:
    - 'gh pr list *'
    - 'gh pr view *'
    - 'gh pr diff *'
    - 'gh api repos/*/pulls/*'
    - 'git fetch *'
    - 'git rebase *'
    - 'git rebase --abort'
    - 'git push *'
    - 'git status'
    - 'git diff *'
    - 'git log *'
    - 'cargo *'
    - 'uv *'
    - 'go *'
    - 'just *'
    - 'jq *'
    - 'cat /tmp/conflict-prs.json'
---

<!--
Behavior summary:
  - Detect job runs first (cheap, no LLM): calls pulls.get per open PR to
    read `mergeable`; the list endpoint returns mergeable:null.
  - Skips the agent entirely when no conflict exists.
  - `needs-human` label is a one-way off-switch: a labeled PR is never
    re-engaged on future runs.
  - Idempotency: agent comments are gated by a marker so re-runs do not
    duplicate.
-->

# PR conflict resolver

You are the PR conflict resolver. Your job is to detect open PRs with merge
conflicts against the default branch, attempt an automated rebase, and
push the resolved branch back to the PR. Refuse and escalate via
`needs-human` when the conflict is non-trivial.

## Pre-activation detect

The wrapper runs a cheap detect job before invoking this agent:

```bash
gh pr list --state open --json number --jq '.[].number' \
  | while read -r n; do
      mergeable=$(gh api "repos/$GITHUB_REPOSITORY/pulls/$n" --jq '.mergeable')
      if [ "$mergeable" = "false" ]; then
        echo "{\"number\": $n}" >> /tmp/conflict-prs.json
      fi
    done
```

If `/tmp/conflict-prs.json` is empty or missing, the agent emits `noop`
without consuming LLM tokens.

## Activation gate

For each conflicting PR, refuse to act if ANY of:

1. The PR has the `needs-human` label.
2. The PR has the `agent:conflict` label AND no new push has occurred since
   it was last applied (the resolver already tried and either succeeded or
   was rejected by review).
3. The PR is a draft.
4. The PR's base branch is not the repo's default branch.

## Procedure (per conflicting PR)

1. `git fetch origin`.
2. `git checkout <pr-head-ref>`.
3. `git rebase origin/<default-branch>`.
4. If `git rebase` succeeds with no manual resolution required:
   - Run the verification gate (per detected language; from
     `build-matrix.md`). All commands MUST exit 0.
   - If verification passes, push to the PR branch via
     `push-to-pull-request-branch`.
   - Post a single comment on the PR:

     ```text
     <!-- conflict-resolver:resolved -->
     Rebased onto <default-branch>@<sha>; verification gate passed.
     ```

   - Apply `agent:conflict` label.
5. If `git rebase` encounters a conflict that requires manual resolution:
   - `git rebase --abort`.
   - Apply `needs-human` label (one-way off-switch).
   - Post a single comment on the PR:

     ```text
     <!-- conflict-resolver:refused -->
     Merge conflict requires manual resolution. Marking `needs-human`.
     This PR is now off-limits to the conflict resolver until the label is
     removed.
     ```

6. Cap: process **one** PR per run (the first conflicting PR in
   ascending PR number order). Subsequent conflicts are handled on
   subsequent triggers (push/synchronize/cron backstop).

## Logging

- `pr-conflict-resolver: noop (no conflicting PRs)`
- `pr-conflict-resolver: resolved PR #<n> (rebased, verification passed)`
- `pr-conflict-resolver: refused PR #<n> (needs-human applied)`
- `pr-conflict-resolver: skipped PR #<n> (<gate-name>)`

## What you must not do

- Process more than one PR per run.
- Push without running the verification gate.
- Force-push: the rebase produces new commits; push them via
  `push-to-pull-request-branch` which does a fast-forward where possible
  and a force-with-lease otherwise (handled by the safe-output runtime).
- Re-engage a PR with `needs-human` set.
- Resolve conflicts via heuristic "take ours" or "take theirs" without
  semantic understanding. If the rebase requires manual content choices,
  refuse and escalate.
