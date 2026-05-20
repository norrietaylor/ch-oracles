# ch-oracles End-to-End Test Runbook

## Mission

Verify the entire `ch-oracles` agentic-workflow suite end-to-end against a real consumer repository. Success means: the installer lands all wrappers and templates correctly; every lint, audit, auto-fix, and worker chore activates as designed; the dedup, verification, and `needs-human` off-switch contracts hold; and the engine split (Copilot for chores, Claude for workers) functions across all 14 workflows. The executing agent should be able to run this runbook with zero prior context from any other conversation.

Target consumer repo: **`gominimal/spectables_test`** (the operator wrote this literally; treat it as canonical until Step 0 confirms or corrects it).

Upstream suite repo: `norrietaylor/ch-oracles` at https://github.com/norrietaylor/ch-oracles.
Docs site: https://norrietaylor.github.io/ch-oracles/.

You are testing 14 workflows in 4 groups:

- **Lint** (engine: copilot, `mode: report|autofix`): `chore-style-rust`, `chore-style-python`, `chore-style-go`, `chore-style-toml`, `chore-style-ncl`
- **Audit** (engine: copilot): `docs-patrol`, `test-coverage-detector`, `dependency-review`
- **Auto-fix** (engine: copilot): `trivial-dep-bump-rust`, `trivial-dep-bump-python`, `trivial-dep-bump-go`
- **Workers** (engine: copilot): `worker-fix`, `worker-iterate`, `pr-conflict-resolver`

Throughout the run, track every workflow run URL, issue number, and PR number you create — the final reporting step requires them.

---

## Step 0 — Confirm the target repo name

The operator wrote `gominimal/spectables_test`, which may be a typo for `spectacles_test`. Verify before doing anything else.

```bash
gh repo view gominimal/spectables_test --json name,owner,visibility 2>&1
gh repo view gominimal/spectacles_test --json name,owner,visibility 2>&1
```

- If `spectables_test` exists, use it as-is.
- If only `spectacles_test` exists, use that and note the correction in your final report.
- If neither exists, stop and emit `needs input:` asking the operator which repo to use, or whether to create one (`gh repo create gominimal/spectables_test --public --clone`).

Record the confirmed slug as `$REPO` for the remainder of the run.

```bash
export REPO="gominimal/spectables_test"   # or whichever the check above confirmed
```

---

## Preconditions

Verify each of these before touching the test repo. If any fails, resolve before continuing — most are blocking.

### P1. GitHub CLI authenticated

```bash
gh auth status
```

Expect: `Logged in to github.com account <name>`. If not, run `gh auth login` and choose `HTTPS` + `Login with a web browser`.

### P2. Admin or maintain access to $REPO

```bash
gh api "repos/$REPO" --jq '.permissions'
```

Expect: `{"admin": true, ...}` or at minimum `"maintain": true`. Without this you cannot set secrets/vars or sync labels. If absent, stop and emit `needs input:` asking the operator to grant access.

### P3. Upstream suite is reachable

```bash
gh repo view norrietaylor/ch-oracles --json visibility,defaultBranchRef
```

Expect: `"visibility":"PUBLIC"` and a default branch (usually `main`). Record the default branch as `$REF` (used in wrapper `uses:` lines).

```bash
export REF="main"
```

### P4. GitHub App exists for the bot identity

The suite expects a GitHub App that posts on the bot's behalf. Confirm one exists and is installed on `$REPO`.

```bash
gh api "repos/$REPO/installation" 2>&1 | head -20
```

Expect a JSON body with `"app_slug"` set. If the response is `Not Found`, stop and emit `needs input:` asking the operator to install the App on the target repo. This is a one-time prerequisite the runbook cannot self-serve.

### P5. Required secrets

The suite reads these secrets from the consumer repo:

| Name | Purpose |
| --- | --- |
| `APP_PRIVATE_KEY` | PEM private key for the GitHub App in P4 |
| `COPILOT_GITHUB_TOKEN` | PAT or App-issued token with Copilot API scope (every workflow in the suite) |

Check which are already set:

```bash
gh secret list -R "$REPO"
```

Set any that are missing. If the operator has not provided values, stop and emit `needs input:` listing exactly which secrets to obtain.

```bash
# Examples — supply real values:
gh secret set APP_PRIVATE_KEY     -R "$REPO" < /path/to/app-key.pem
gh secret set COPILOT_GITHUB_TOKEN -R "$REPO" --body "<token>"
```

### P6. Required vars

```bash
gh variable list -R "$REPO"
```

Required: `APP_ID` (the numeric App ID matching `APP_PRIVATE_KEY`). Optional: `CH_ORACLES_LANGUAGE` (overrides language auto-detect for polyglot workers; values: `rust`, `python`, `go`, or a comma-separated list).

```bash
gh variable set APP_ID -R "$REPO" --body "<numeric-app-id>"
# Optional:
gh variable set CH_ORACLES_LANGUAGE -R "$REPO" --body "python"
```

### P7. Local working directory

Pick a scratch directory you can write to.

```bash
export WORK="$HOME/tmp/ch-oracles-e2e-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$WORK"
cd "$WORK"
```

---

## Stage A — Install

Goal: run `scripts/quick-setup.sh` from `norrietaylor/ch-oracles` against `$REPO`, verify every artifact lands, and open the install PR.

### A1. Clone test repo

```bash
gh repo clone "$REPO" "$WORK/repo"
cd "$WORK/repo"
git checkout -b e2e/ch-oracles-install
```

### A2. Dry run quick-setup

Fetch the installer from upstream and execute in dry-run mode. This must touch nothing on disk.

```bash
curl -fsSL "https://raw.githubusercontent.com/norrietaylor/ch-oracles/$REF/scripts/quick-setup.sh" \
  -o /tmp/ch-oracles-quick-setup.sh
chmod +x /tmp/ch-oracles-quick-setup.sh

/tmp/ch-oracles-quick-setup.sh \
  --suite oracles \
  --with-workers \
  --dry-run \
  2>&1 | tee /tmp/ch-oracles-dry-run.log
```

**Success criteria:**

- Exit code 0.
- Log lists every wrapper it *would* write under `.github/workflows/`.
- An auto-detect line names at least one language (`rust`, `python`, `go`, `toml`, `ncl`). Cross-check against actual repo contents:

```bash
ls "$WORK/repo" | grep -E '(Cargo\.toml|pyproject\.toml|go\.mod|setup\.py|requirements\.txt)' || echo "no manifests found"
```

If auto-detect found nothing and there are no manifests, jump to Failure-Mode F1 below and seed a minimal manifest before continuing.

### A3. Real install

```bash
/tmp/ch-oracles-quick-setup.sh \
  --suite oracles \
  --with-workers \
  2>&1 | tee /tmp/ch-oracles-install.log
```

**Success criteria** — each must be present:

```bash
ls .github/workflows/ | sort
# Expect: chore-style-{rust,python,go,toml,ncl}.yml,
#         docs-patrol.yml, test-coverage-detector.yml, dependency-review.yml,
#         trivial-dep-bump-{rust,python,go}.yml,
#         worker-fix.yml, worker-iterate.yml, pr-conflict-resolver.yml

ls .github/
# Expect AGENTS.md, labels.yml, copilot-instructions.md, ISSUE_TEMPLATE/

cat .github/AGENTS.md | grep -E '<!-- ch-oracles:(start|end) -->' | wc -l
# Expect: 2 (start + end markers present)

cat .github/AGENTS.md | grep -E 'build-commands' | head -3
# Expect: a "Build commands" override section to be present
```

### A4. Verify wrapper references

Every wrapper must call the hosted `.lock.yml` at the correct ref.

```bash
for f in .github/workflows/*.yml; do
  echo "=== $f ==="
  grep -E 'uses:\s*norrietaylor/ch-oracles/.github/workflows/.*\.lock\.yml@' "$f" \
    || echo "MISSING lock.yml uses: in $f"
done
```

**Success criteria:** every workflow file matches `uses: norrietaylor/ch-oracles/.github/workflows/<chore>.lock.yml@<REF>`. Any `MISSING` line is a failure — check Failure-Mode F4.

### A5. Sync labels

```bash
gh label clone norrietaylor/ch-oracles -R "$REPO" --force 2>&1 | tail -20
# OR if you have a label-sync action: rely on labels.yml in the PR
```

Verify the expected taxonomy is present:

```bash
gh label list -R "$REPO" --limit 100 \
  | grep -E 'agent:(lint:(rust|python|go|toml|ncl)|doc-drift|coverage|dep-drift|auto-merge|autofix|conflict)|needs-human'
```

**Success criteria:** all of `agent:lint:rust`, `agent:lint:python`, `agent:lint:go`, `agent:lint:toml`, `agent:lint:ncl`, `agent:doc-drift`, `agent:coverage`, `agent:dep-drift`, `agent:auto-merge`, `agent:autofix`, `agent:conflict`, `needs-human` are listed.

### A6. Commit and open install PR

```bash
git add .github/
git -c commit.gpgsign=false commit -m "Install ch-oracles suite via quick-setup"
git push -u origin e2e/ch-oracles-install

gh pr create \
  --repo "$REPO" \
  --title "Install ch-oracles (E2E test)" \
  --body "Automated install via scripts/quick-setup.sh for end-to-end test."
INSTALL_PR=$(gh pr view --repo "$REPO" --json number --jq '.number')
echo "Install PR: #$INSTALL_PR"
```

**Success criteria:** PR opens, no CI errors caused by the install itself, all workflow files validate (no `gh actions ... lint` failures). Record `$INSTALL_PR`. Merge it once green:

```bash
gh pr merge "$INSTALL_PR" --repo "$REPO" --squash --auto
```

Wait for the merge before moving on (subsequent stages need workflows on `main`):

```bash
until [ "$(gh pr view "$INSTALL_PR" --repo "$REPO" --json state --jq '.state')" = "MERGED" ]; do sleep 10; done
git fetch origin main && git checkout main && git pull
```

---

## Stage B — Lint chore (report mode)

Pick the language that auto-detect surfaced in A2. The example below uses **Python**; substitute `rust`, `go`, `toml`, or `ncl` if a different language was detected.

### B1. Plant a deliberate violation

Create a working branch and add a file with a known lint failure.

```bash
git checkout -b e2e/lint-report
mkdir -p src
cat > src/bad_imports.py <<'PY'
"""Deliberate lint violation for ch-oracles E2E."""
from os import *  # noqa: deliberate star-import for E2E
def unused(): return getcwd()
PY
git add src/bad_imports.py
git -c commit.gpgsign=false commit -m "test: plant python lint violation"
git push -u origin e2e/lint-report
```

Equivalent violation seeds for other languages:

- **Rust:** `let foo = 1;` (unused, no leading underscore) in `src/main.rs`
- **Go:** an unused import (`import "fmt"` with no `fmt.*` reference)
- **TOML:** trailing whitespace plus mixed tabs/spaces in any `*.toml`
- **NCL:** a syntactically invalid `.ncl` (`{ x = ; }`)

### B2. Trigger the lint chore in report mode

```bash
gh workflow run chore-style-python.yml \
  --repo "$REPO" \
  --ref e2e/lint-report \
  -f mode=report

# Poll for completion
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow chore-style-python.yml \
           --branch e2e/lint-report --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
```

**Success criteria:** exit status 0; run conclusion is `success`. Save `$RUN_ID`.

### B3. Verify exactly one issue was filed

```bash
gh issue list --repo "$REPO" --label "agent:lint:python" --state open --json number,title,body,updatedAt
```

**Success criteria:**

- Exactly one issue matches `agent:lint:python`.
- Its body's first non-blank line is `<!-- finding-id: chore-style-python::python::<identity> -->`.

Record the issue number as `$LINT_ISSUE` and the `updatedAt` timestamp as `$T1`.

### B4. Verify dedup on re-run

```bash
gh workflow run chore-style-python.yml --repo "$REPO" --ref e2e/lint-report -f mode=report
sleep 5
RUN_ID2=$(gh run list --repo "$REPO" --workflow chore-style-python.yml \
            --branch e2e/lint-report --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID2" --repo "$REPO" --exit-status
```

After completion:

```bash
COUNT=$(gh issue list --repo "$REPO" --label "agent:lint:python" --state open --json number --jq 'length')
T2=$(gh issue view "$LINT_ISSUE" --repo "$REPO" --json updatedAt --jq '.updatedAt')
echo "count=$COUNT t1=$T1 t2=$T2"
```

**Success criteria:** `COUNT == 1` (no duplicate filed) AND `T2 > T1` (the existing issue was updated, not recreated).

**On failure:** if `COUNT == 2`, the finding-id marker logic broke; dump both issue bodies and check the marker line is byte-identical. If `T2 == T1`, the update path didn't fire; inspect the run logs for `update-issue` vs `create-issue`.

---

## Stage C — Lint chore (autofix mode)

### C1. Trigger autofix

```bash
gh workflow run chore-style-python.yml --repo "$REPO" --ref e2e/lint-report -f mode=autofix
sleep 5
RUN_ID3=$(gh run list --repo "$REPO" --workflow chore-style-python.yml \
            --branch e2e/lint-report --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID3" --repo "$REPO" --exit-status
```

### C2. Verify autofix PR

```bash
gh pr list --repo "$REPO" --label "agent:autofix" --state open \
  --json number,title,body,labels,headRefName
```

**Success criteria:**

- Exactly one PR opens.
- Labels include both `agent:autofix` AND `agent:lint:python`.
- The body contains `Closes #<LINT_ISSUE>`.
- The diff actually removes the `from os import *` line (or replaces with a named import).

Record the PR number as `$AUTOFIX_PR`.

### C3. Verify the verification gate ran before PR open

```bash
gh run view "$RUN_ID3" --repo "$REPO" --log 2>&1 \
  | grep -E '(python-build-commands|verification gate|pytest|ruff)' | head -20
```

**Success criteria:** at least one of the language-specific build commands (defaults loaded from `python-build-commands.md` in upstream `shared/`) executed and passed prior to the PR being opened. If no build commands ran, the gate was skipped — record as a failure.

### C4. Merge and verify issue auto-closes

```bash
gh pr merge "$AUTOFIX_PR" --repo "$REPO" --squash
sleep 10
STATE=$(gh issue view "$LINT_ISSUE" --repo "$REPO" --json state --jq '.state')
echo "issue state=$STATE"
```

**Success criteria:** `STATE == "CLOSED"`.

---

## Stage D — Audit chores

Run all three audit chores. For each, seed an opportunity if the repo doesn't already have one.

### D1. docs-patrol

Plant a doc-drift opportunity:

```bash
git checkout -b e2e/audit
# Rename a real file, leave README pointing at the old path
git mv src/bad_imports.py src/bad_imports_renamed.py 2>/dev/null || true
cat >> README.md <<'MD'

## Module overview

The `src/bad_imports.py` module demonstrates star-imports (intentionally bad).
MD
git -c commit.gpgsign=false commit -am "test: plant doc-drift" && git push -u origin e2e/audit

gh workflow run docs-patrol.yml --repo "$REPO" --ref e2e/audit
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow docs-patrol.yml --branch e2e/audit --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status

gh issue list --repo "$REPO" --label "agent:doc-drift" --state open --json number,title,body
```

**Success criteria:** at least one open issue with label `agent:doc-drift` whose body starts with `<!-- finding-id: docs-patrol::...::... -->`. Record as `$DOC_ISSUE`.

### D2. test-coverage-detector

Plant an uncovered, non-trivial function (cyclomatic complexity > 5):

```bash
cat > src/uncovered.py <<'PY'
def branchy(x, y, z):
    """Six branches, zero tests — should be flagged."""
    if x > 0:
        if y > 0:
            if z > 0: return "pos-pos-pos"
            else:     return "pos-pos-neg"
        else:
            if z > 0: return "pos-neg-pos"
            else:     return "pos-neg-neg"
    else:
        if y > 0:
            if z > 0: return "neg-pos-pos"
            else:     return "neg-pos-neg"
        else:
            return "neg-neg-any"
PY
git add src/uncovered.py
git -c commit.gpgsign=false commit -m "test: plant uncovered branchy fn" && git push

gh workflow run test-coverage-detector.yml --repo "$REPO" --ref e2e/audit
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow test-coverage-detector.yml --branch e2e/audit --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status

gh issue list --repo "$REPO" --label "agent:coverage" --state open --json number,title --jq 'length'
```

**Success criteria:** between 1 and 3 issues opened with label `agent:coverage` (3 is the documented cap). Each body has a `<!-- finding-id: test-coverage-detector::... -->` marker.

### D3. dependency-review

Pin a deliberately-outdated direct dep so the chore has something to flag:

```bash
# Example for Python — substitute language-appropriate manifest if needed.
echo 'requests==2.20.0' >> requirements.txt
git -c commit.gpgsign=false commit -am "test: outdated direct dep" && git push

gh workflow run dependency-review.yml --repo "$REPO" --ref e2e/audit
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow dependency-review.yml --branch e2e/audit --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status

gh issue list --repo "$REPO" --label "agent:dep-drift" --state open --json number,title
```

**Success criteria:** at least one open issue with `agent:dep-drift`. If the chore returned zero findings, double-check the manifest was committed and the dep is genuinely outdated (`pip index versions requests`).

---

## Stage E — trivial-dep-bump

### E1. Trigger the language-appropriate bump

```bash
# Example for Python; substitute trivial-dep-bump-rust / -go as needed
gh workflow run trivial-dep-bump-python.yml --repo "$REPO" --ref main
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow trivial-dep-bump-python.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
```

### E2. Evaluate outcome

```bash
gh pr list --repo "$REPO" --label "agent:auto-merge" --state open \
  --json number,title,body,labels,autoMergeRequest
```

**Success criteria — one of:**

- **(a)** A PR opened with title matching `chore(deps): patch-level python bumps`, labels include `agent:auto-merge`, and `autoMergeRequest` is non-null (auto-merge is enabled by the safe-output runtime). Record as `$BUMP_PR`.
- **(b)** No PR opened, AND the run log contains an explicit rejection line such as `no patch-level updates available`, `transitive-only change refused`, `yanked release refused`, or `pyproject mutation refused`. Capture the exact line.

If neither (a) nor (b): the chore silently failed; treat as a failure.

### E3. If (a): verify auto-merge completes

```bash
until [ "$(gh pr view "$BUMP_PR" --repo "$REPO" --json state --jq '.state')" = "MERGED" ]; do
  echo "waiting for $BUMP_PR to merge..."; sleep 30
done
```

**Success criteria:** consumer CI on the bump PR turns green and auto-merge fires without human intervention.

---

## Stage F — Worker pickup

### F1. Choose a worker-eligible issue

Pick any open issue from Stage B or Stage D that the worker can act on. Preference order: the `$DOC_ISSUE` from D1 (small, well-scoped) or a fresh `agent:lint:<lang>` issue if `$LINT_ISSUE` was already closed in C4.

```bash
echo "Worker target issue: #$DOC_ISSUE"
```

### F2. Wait for worker-fix or invoke it

```bash
gh workflow run worker-fix.yml --repo "$REPO" --ref main -f issue_number="$DOC_ISSUE"
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow worker-fix.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
```

### F3. Verify the worker PR

```bash
gh pr list --repo "$REPO" --search "in:title [worker:" --state open \
  --json number,title,body,labels,autoMergeRequest
```

**Success criteria:**

- Exactly one open PR whose title starts with `[worker:<label>] ...`.
- Body contains `Closes #<DOC_ISSUE>`.
- `autoMergeRequest` is non-null (declarative auto-merge enabled).

Record as `$WORKER_PR`.

### F4. Verify the verification gate ran

```bash
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 \
  | grep -E '(build-commands|verification gate|pass|fail)' | head -20
```

**Success criteria:** the per-language build matrix (e.g., `python-build-commands.md` defaults if Python was detected) executed and passed before the PR was opened. Confirm the detected language matches your expectation:

```bash
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 | grep -E 'language detected|CH_ORACLES_LANGUAGE' | head -5
```

Per ADR-0004, detection precedence is `vars.CH_ORACLES_LANGUAGE` → AGENTS.md override → manifest sniff. If `CH_ORACLES_LANGUAGE` is set, that string should win.

---

## Stage G — Worker iterate

### G1. Post an actionable review comment

```bash
gh pr review "$WORKER_PR" --repo "$REPO" \
  --comment --body "Please add a one-line module docstring at the top of the changed file."
```

### G2. Wait for worker-iterate

```bash
sleep 30
RUN_ID=$(gh run list --repo "$REPO" --workflow worker-iterate.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
```

**Activation gate:** the workflow only runs if the PR title starts with `[worker:`, the PR author is the worker bot, AND a human reviewer commented. Verify the gate decision in the logs:

```bash
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 | grep -E '(gate|skipped|activated)' | head -10
```

### G3. Verify the addressed marker

```bash
gh pr view "$WORKER_PR" --repo "$REPO" --comments --json comments \
  --jq '.comments[].body' | grep -E 'worker-iterate:addressed'

# Verify a new commit was pushed
gh pr view "$WORKER_PR" --repo "$REPO" --json commits --jq '.commits | length'
```

**Success criteria:** at least one comment body contains `<!-- worker-iterate:addressed -->`, AND commits count increased by one.

### G4. Verify verification gate ran before push

```bash
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 \
  | grep -E '(verification gate|build-commands)' | head -10
```

**Success criteria:** the gate ran and passed before the new commit was pushed. A push that bypasses the gate is a failure.

### G5. Post a non-actionable opinion

```bash
gh pr review "$WORKER_PR" --repo "$REPO" \
  --comment --body "nit: I'd prefer different wording, but no strong opinion."
sleep 30
RUN_ID2=$(gh run list --repo "$REPO" --workflow worker-iterate.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID2" --repo "$REPO" --exit-status
```

### G6. Verify the declined marker

```bash
gh pr view "$WORKER_PR" --repo "$REPO" --comments --json comments \
  --jq '.comments[].body' | grep -E 'worker-iterate:declined'

# Commit count should NOT have advanced
gh pr view "$WORKER_PR" --repo "$REPO" --json commits --jq '.commits | length'
```

**Success criteria:** at least one comment with `<!-- worker-iterate:declined -->`, AND commit count unchanged from after G3.

### G7. Verify caps

Documented caps: 3 comments addressed per single run, 5 runs total per PR.

```bash
# Total worker-iterate runs for this PR
gh run list --repo "$REPO" --workflow worker-iterate.yml --limit 20 \
  --json databaseId,headBranch \
  --jq "[.[] | select(.headBranch | startswith(\"$(gh pr view "$WORKER_PR" --repo "$REPO" --json headRefName --jq '.headRefName')\"))] | length"
```

**Success criteria:** if this count reaches 5, the next trigger must produce a `worker-iterate:cap-exhausted` (or equivalent) log line and not push.

---

## Stage H — pr-conflict-resolver

### H1. Force a merge conflict

```bash
git checkout main && git pull

# Read a file the worker likely modified, then change the same lines on main
WORKER_BRANCH=$(gh pr view "$WORKER_PR" --repo "$REPO" --json headRefName --jq '.headRefName')
CHANGED_FILE=$(gh pr view "$WORKER_PR" --repo "$REPO" --json files --jq '.files[0].path')

git checkout -b e2e/force-conflict
# Append a conflicting line at the same region the worker touched
echo "// conflict-marker $(date +%s)" >> "$CHANGED_FILE"
git -c commit.gpgsign=false commit -am "test: force conflict for resolver"
git push -u origin e2e/force-conflict

gh pr create --repo "$REPO" --title "Force conflict" --body "E2E conflict source"
CONFLICT_PR=$(gh pr view --repo "$REPO" --json number --jq '.number')
gh pr merge "$CONFLICT_PR" --repo "$REPO" --squash --admin
```

Confirm the worker PR is now non-mergeable:

```bash
sleep 30
gh api "repos/$REPO/pulls/$WORKER_PR" --jq '{mergeable, mergeable_state}'
```

Expect `mergeable: false` or `mergeable_state: "dirty"`.

### H2. Trigger pr-conflict-resolver

The push-to-main may have already triggered it; if not, invoke explicitly:

```bash
gh workflow run pr-conflict-resolver.yml --repo "$REPO" --ref main -f pr_number="$WORKER_PR"
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow pr-conflict-resolver.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
```

### H3. Verify the cheap detect job ran first

```bash
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 \
  | grep -E '(detect|pulls\.get|mergeable)' | head -10
```

**Success criteria:** a non-LLM `detect` job ran before the resolver job, queried the GitHub API (`pulls.get .mergeable`), and reported the conflict.

### H4. Verify resolver outcome

```bash
gh pr view "$WORKER_PR" --repo "$REPO" --comments --json comments,labels \
  --jq '{labels: .labels, comments: [.comments[].body]}'
```

**Success criteria — one of:**

- **(a)** A comment contains `<!-- conflict-resolver:resolved -->`, labels include `agent:conflict`, AND a new commit was pushed to the worker branch that rebases cleanly:
  ```bash
  gh api "repos/$REPO/pulls/$WORKER_PR" --jq '.mergeable'   # expect: true
  ```
- **(b)** A comment contains `<!-- conflict-resolver:refused -->` AND labels include `needs-human`. This is correct behavior for non-trivial conflicts.

### H5. If (b), verify the one-way off-switch

```bash
# Trigger again; resolver must NOT re-engage
gh workflow run pr-conflict-resolver.yml --repo "$REPO" --ref main -f pr_number="$WORKER_PR"
sleep 5
RUN_ID=$(gh run list --repo "$REPO" --workflow pr-conflict-resolver.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO" --exit-status
gh run view "$RUN_ID" --repo "$REPO" --log 2>&1 | grep -E 'needs-human|skipped|off-switch' | head -5
```

**Success criteria:** log shows the workflow detected `needs-human` and exited without further action. The PR's comment count and commit count must not change.

---

## Stage I — Coexistence (optional)

Run only if the operator wants `norrietaylor/spectacles` installed alongside ch-oracles in the same repo. Skip otherwise.

### I1. Install spectacles

```bash
curl -fsSL "https://raw.githubusercontent.com/norrietaylor/spectacles/main/scripts/quick-setup.sh" \
  -o /tmp/spectacles-setup.sh
chmod +x /tmp/spectacles-setup.sh
cd "$WORK/repo"
git checkout -b e2e/spectacles-coexist
/tmp/spectacles-setup.sh 2>&1 | tee /tmp/spectacles-install.log
```

### I2. Verify AGENTS.md coexistence

```bash
grep -E '<!-- (ch-oracles|spectacles):(start|end) -->' .github/AGENTS.md
```

**Success criteria:** both sets of start/end markers present, neither block has overwritten the other (per ADR-0003).

### I3. Verify labels merged

```bash
gh label list -R "$REPO" --limit 200 | wc -l   # capture pre-install count separately
```

**Success criteria:** all ch-oracles labels still exist; spectacles-specific labels added on top with no removals.

### I4. Verify no wrapper collisions

```bash
ls .github/workflows/ | sort | uniq -d
```

**Success criteria:** zero duplicate filenames.

### I5. Verify `needs-human` is cross-honored

Label any open agent-touchable issue with `needs-human` and trigger one workflow from each suite; both must skip the issue.

```bash
gh issue edit <some-issue> --repo "$REPO" --add-label "needs-human"
# Trigger one ch-oracles chore + one spectacles agent; verify both log "needs-human off-switch honored"
```

---

## Stage J — Cleanup

Choose one of the two paths below.

### J1. Roll back (preserve the repo)

```bash
git checkout main && git pull
git branch -D e2e/ch-oracles-install e2e/lint-report e2e/audit e2e/force-conflict e2e/spectacles-coexist 2>/dev/null
git push origin --delete e2e/lint-report e2e/audit e2e/force-conflict e2e/spectacles-coexist 2>/dev/null

# Close any leftover test issues
for n in $LINT_ISSUE $DOC_ISSUE; do
  [ -n "$n" ] && gh issue close "$n" --repo "$REPO" --comment "E2E test complete" 2>/dev/null
done
```

### J2. Delete (only if the repo was created solely for this run)

```bash
gh repo delete "$REPO" --confirm
```

### J3. Document final state

Regardless of path, record in the final report: which branches remain, which PRs are open/merged, which issues are open/closed, and whether secrets/vars are still set.

---

## Failure-Mode Guidance

### F1. quick-setup auto-detect found nothing

The installer needs at least one language manifest to detect a stack. Seed the smallest valid manifest for the language you want to test, then re-run `--dry-run`:

```bash
# Python
echo 'requests>=2.0' > requirements.txt
# Rust
cat > Cargo.toml <<'TOML'
[package]
name = "stub"
version = "0.0.1"
edition = "2021"
TOML
mkdir -p src && echo 'fn main() {}' > src/main.rs
# Go
go mod init example.com/stub
```

Commit the manifest, then re-run `quick-setup.sh --dry-run` and confirm detection.

### F2. Bot lacks repo install access

Symptom: `gh api repos/$REPO/installation` returns 404, or workflow runs fail with `Resource not accessible by integration`. The GitHub App from Precondition P4 is not installed on `$REPO`.

Fix: in the GitHub UI, navigate to the App's installation settings (`https://github.com/apps/<app-slug>/installations/new`) and grant it access to `$REPO`. Confirm:

```bash
gh api "repos/$REPO/installation" --jq '.app_slug'   # must return a slug
```

### F3. Chore times out or 0-tokens from Copilot

Symptom: run conclusion `failure`, logs contain `429 rate limit`, `quota exceeded`, `0 tokens remaining`, or no Copilot response after timeout.

Triage:
- Re-run once: `gh run rerun <RUN_ID> --repo "$REPO"`. Transient API blips are common.
- If still failing, verify the relevant secret is set and not expired (`gh secret list -R "$REPO"`).
- If failing across multiple chores, the upstream provider is degraded — pause the run, note the time, and resume later.

### F4. Lock-file `uses:` reference 404s

Symptom: workflow refuses to start; log shows `unable to find reusable workflow ... at ref <ref>`.

Cause: the `@<ref>` pinned in the wrapper doesn't exist on `norrietaylor/ch-oracles`.

Fix: either re-run quick-setup with `--ref <known-good-tag>`, or hand-edit each wrapper to pin to `@main` or a published tag:

```bash
# Pin all wrappers to main as a temporary measure
sed -i.bak -E 's|@[^ ]+$|@main|' .github/workflows/*.yml
git -c commit.gpgsign=false commit -am "fix: re-pin ch-oracles wrappers to main" && git push
```

### F5. Generic failure stops

If three independent stages fail in succession, halt the run. Capture all run URLs, escalate to the operator, and emit a structured report (next section) flagging the stages that didn't execute.

---

## Reporting

At the end of the run, emit a structured report. Use the table form unless the operator explicitly asked for JSON.

### Markdown table form

```markdown
| Stage | Status   | Evidence                                                                | Notes                                                        |
|-------|----------|-------------------------------------------------------------------------|--------------------------------------------------------------|
| 0     | pass     | repo: gominimal/spectables_test                                         | confirmed spelling                                           |
| A     | pass     | PR #<INSTALL_PR>                                                        | quick-setup landed all 14 wrappers                           |
| B     | pass     | issue #<LINT_ISSUE>, runs <RUN_ID>, <RUN_ID2>                           | dedup verified, updated_at advanced                          |
| C     | pass     | PR #<AUTOFIX_PR>                                                        | gate ran, issue auto-closed on merge                         |
| D     | pass     | issues #<DOC_ISSUE>, #<COV_ISSUE...>, #<DEP_ISSUE>                      | all three audit labels filed                                 |
| E     | pass(a)  | PR #<BUMP_PR>, run <RUN_ID>                                             | auto-merged                                                  |
| F     | pass     | PR #<WORKER_PR>, run <RUN_ID>                                           | language detected: python; verification gate green           |
| G     | pass     | comments on PR #<WORKER_PR>, runs <RUN_ID>, <RUN_ID2>                   | addressed + declined markers both present; caps honored      |
| H     | pass(b)  | PR #<WORKER_PR>                                                         | resolver refused, needs-human applied, off-switch honored    |
| I     | skipped  | -                                                                       | operator did not request spectacles coexistence              |
| J     | pass     | -                                                                       | branches rolled back; repo preserved                         |
```

### JSON form (alternate)

```json
{
  "repo": "gominimal/spectables_test",
  "ref": "main",
  "started_at": "<ISO8601>",
  "finished_at": "<ISO8601>",
  "stages": {
    "A": {"status": "pass", "evidence": {"install_pr": 0}, "notes": ""},
    "B": {"status": "pass", "evidence": {"issue": 0, "runs": [0, 0]}, "notes": ""},
    "C": {"status": "pass", "evidence": {"pr": 0}, "notes": ""},
    "D": {"status": "pass", "evidence": {"doc_issue": 0, "cov_issues": [0], "dep_issue": 0}, "notes": ""},
    "E": {"status": "pass", "evidence": {"pr": 0, "outcome": "a"}, "notes": ""},
    "F": {"status": "pass", "evidence": {"pr": 0, "detected_language": "python"}, "notes": ""},
    "G": {"status": "pass", "evidence": {"runs": [0, 0]}, "notes": ""},
    "H": {"status": "pass", "evidence": {"pr": 0, "outcome": "b"}, "notes": ""},
    "I": {"status": "skipped", "evidence": null, "notes": "not requested"},
    "J": {"status": "pass", "evidence": null, "notes": "branches deleted"}
  },
  "escalations": [],
  "operator_actions_required": []
}
```

Use `status` values: `pass`, `fail`, `skipped`, `partial`. Populate `escalations` with anything the operator must address (provider outages, missing GitHub App, etc.) and `operator_actions_required` with concrete next steps.

---

## End of runbook

Once the report is emitted, the run is complete. Do not commit anything else to `$REPO` or push to `norrietaylor/ch-oracles`. If any stage emitted `fail` or `partial`, surface it prominently in the report's top line so the operator sees it before scanning the table.
