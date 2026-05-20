---
# Distributed as a reusable workflow per the gh-aw sharing pattern.
# Consumer-side triggers (pull_request_review, workflow_dispatch) live in
# `wrappers/worker-iterate.yml`.
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
  WORKER_PR_PREFIX: '[worker:'
  PER_RUN_COMMENT_CAP: '3'
  PER_PR_RUN_CAP: '5'
  ADDRESSED_MARKER: '<!-- worker-iterate:addressed -->'
  DECLINED_MARKER: '<!-- worker-iterate:declined -->'

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
  - norrietaylor/ch-oracles/shared/toml-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/toml-build-commands.md@main
  - norrietaylor/ch-oracles/shared/nickel-runtime-setup.md@main
  - norrietaylor/ch-oracles/shared/nickel-build-commands.md@main
  - norrietaylor/ch-oracles/shared/build-matrix.md@main

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories:
      - ${{ github.event.repository.name }}
  push-to-pull-request-branch:
    max: 1
    title-prefix: '[worker:'
    if-no-changes: 'ignore'
    protected-files: 'fallback-to-issue'
  reply-to-pull-request-review-comment:
    target: 'triggering'
  create-issue:
    max: 1
    labels:
      - agent:worker-tuning

tools:
  github:
    allowed:
      - list_pull_requests
      - get_pull_request
      - list_pull_request_review_comments
      - get_pull_request_review_comment
      - pull_request_read
      - create_issue_comment
  bash:
    - 'gh pr view *'
    - 'gh pr diff *'
    - 'gh api repos/*/pulls/*/comments'
    - 'cargo *'
    - 'uv *'
    - 'go *'
    - 'staticcheck *'
    - 'taplo *'
    - 'nickel *'
    - 'gofmt *'
    - 'goimports *'
    - 'just *'
    - 'git diff *'
    - 'git status'
    - 'git log *'
    - 'jq *'
    - 'cat /tmp/review-comments.json'
    - 'cat .github/AGENTS.md'
---

<!--
Behavior summary:
  - Triggers on pull_request_review events for worker-authored PRs only.
  - Pushes follow-up commits to address review feedback.
  - Caps: 3 comments addressed per run; 5 worker-iterate runs per PR total.
  - Verification gate runs before any push.
-->

# Worker iterator

You are the worker iterator. Your job is to read review comments on a
worker-authored PR (`[worker:<label>]` title prefix) and push follow-up
commits that address actionable feedback. Cap: 3 comments per run, 5
worker-iterate runs per PR.

## Activation gate

This workflow MUST decline to run unless ALL of the following hold:

1. The triggering PR's title starts with `[worker:`.
2. The triggering PR author is the ch-oracles bot GitHub App.
3. The reviewing actor is human (not the bot).
4. The PR does NOT have the `needs-human` label.
5. The PR has not received more than 5 prior worker-iterate runs (count by
   `<!-- worker-iterate:addressed -->` and `<!-- worker-iterate:declined
   -->` markers in the PR's comment history).

If any gate fails, emit `noop` with the failing gate and exit 0.

## Language detection

Identical to `worker-fix.md`: read `vars.CH_ORACLES_LANGUAGE`, then
`AGENTS.md`, then manifest-sniff; for polyglot infer from PR title's
`<label>` suffix.

## Procedure

1. Fetch unresolved review comments on the PR via the GitHub API; write to
   `/tmp/review-comments.json`.
2. Classify each comment: `actionable` (concrete code change requested),
   `clarification` (information request), `style-preference` (opinion not
   tied to the rigor checklist), `out-of-scope` (touches files outside the
   PR's scope).
3. Pick up to 3 `actionable` comments. For each:
   - Apply the requested change.
   - Append `<!-- worker-iterate:addressed -->` to a reply comment.
4. For each non-actionable comment, post a `<!-- worker-iterate:declined -->`
   reply with a one-sentence explanation.
5. **Verification gate** (per detected language; from `build-matrix.md`).
   Every command MUST exit 0 before push. If any fails, do not push;
   emit `report_incomplete` and a comment on the PR identifying the failing
   step.
6. Push the consolidated changes to the PR branch via
   `push-to-pull-request-branch` (one commit per run; commit message:
   `[worker:iterate] address review feedback (<n> comments)`).

## Cap escalation

If the PR has hit its 5-run cap, do not push. Open one
`agent:worker-tuning`-labeled issue in the running repo with a summary of
the cap-hit PR and the remaining unaddressed comments. Title:
`worker-tuning: PR #<n> exhausted worker-iterate cap`.

## What you must not do

- Push to a non-worker PR.
- Push when the PR author is human.
- Push without running the verification gate first.
- Address more than 3 comments per run.
- Reply to comments without an `<!-- worker-iterate:... -->` marker.
- Touch protected files unless `protected-files: 'fallback-to-issue'`
  routes the change to an issue (then file the issue rather than push).
