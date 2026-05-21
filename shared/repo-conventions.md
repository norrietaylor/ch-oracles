## Per-repo conventions

Every ch-oracles chore imports this fragment so it can reference repo-specific
conventions without repeating them in every workflow prompt.

### Canonical doc surface

If the repository contains an `AGENTS.md` file under `.github/`, treat its
content as authoritative for:

- Build, test, and lint commands (see the `## Build Commands (ch-oracles
  override)` section, if present).
- Code style and linting rules beyond what the language defaults specify.
- PR conventions (commit format, branch naming).
- Domain-specific constraints.

Read `.github/AGENTS.md` before beginning any analysis or change. If it
contradicts the code, flag the discrepancy rather than silently preferring
one over the other.

If no `.github/AGENTS.md` is present, fall back to `README.md` for
project-level conventions, then to language defaults from
`shared/build-matrix.md`.

### Branch and commit conventions

Unless `AGENTS.md` specifies otherwise:

- Branch names: `chore/<short-description>` for maintenance work,
  `fix/<short-description>` for bug fixes, `worker/<label>/<issue-num>` for
  worker-emitted fix branches.
- Commit messages: imperative mood, present tense, 72-character limit on the
  subject line.
- PR titles: same format as commit messages, with the chore prefix where
  applicable (e.g., `chore(deps): patch-level bumps`, `[worker:doc-drift] ...`).
- Do not force-push to any branch that has an open PR.

### Label conventions

ch-oracles owns the following label namespaces:

| Label | Meaning |
|---|---|
| `agent:lint:<lang>` | Lint/style finding for the named language (rust, python, go, toml, ncl). |
| `agent:tidy:<lang>` | Reserved for future deeper static-analysis chores. |
| `agent:doc-drift` | Documentation is out of sync with code. |
| `agent:coverage` | Test coverage gap detected. |
| `agent:dep-drift` | Dependency needs review or update. |
| `agent:auto-merge` | Informational. Applied to trivial-dep-bump PRs alongside the gh-aw declarative auto-merge. |
| `agent:autofix` | Applied to PRs from `chore-style-*.md` in `mode: autofix`. |
| `agent:conflict` | Applied by `pr-conflict-resolver` to PRs it has rebased. |

ch-oracles honors but does not own:

| Label | Meaning |
|---|---|
| `needs-human` | Cross-suite hand-off label. When set, ch-oracles workers decline to act on the item. Owned by `gominimal/spectacles` when co-installed. |

Apply the most specific label that matches the finding. If none match, do not
apply an agent label.

### Issue and PR hygiene

- Search for an existing open issue before creating a new one (see
  `safe-output-create-issue.md`).
- Close the corresponding issue when opening a fix PR, using `Closes #<n>` in
  the PR description.
- Do not assign issues or PRs to individuals unless `AGENTS.md` specifies an
  assignment policy.
- Do not request reviews from individuals unless `AGENTS.md` specifies a
  review policy.

### Language-specific notes

Per-language toolchain conventions (Rust edition, Python interpreter, Go
version, Nickel binary version) are sourced from `shared/build-matrix.md`
with `AGENTS.md` overrides taking precedence. See the individual
`shared/<lang>-runtime-setup.md` fragments for runner provisioning details.
