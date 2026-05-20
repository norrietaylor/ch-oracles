## Runtime environment setup

Apply the following setup steps at the start of any agent workflow step that
reads from or writes to the repository.

### 1. Verify checkout

Confirm the repository has been checked out before the agent step runs:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
```

Use `fetch-depth: 0` for workflows that traverse commit history (doc-drift,
test-coverage detector). Use `fetch-depth: 1` for workflows that only need
the current HEAD (lint, dep-bump).

### 2. Set up git identity

Configure a non-interactive git identity so the agent can commit changes
without prompts:

```bash
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
```

### 3. Confirm tool availability

Before the agent step begins, confirm the expected tools are on PATH:

```bash
command -v gh >/dev/null 2>&1 || { echo "gh CLI not found" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq not found" >&2; exit 1; }
gh aw --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | awk -F. '
  ($1 > 0) || ($1 == 0 && $2 > 72) || ($1 == 0 && $2 == 72 && $3 >= 0) { found=1 }
  END { if (!found) { print "gh aw v0.72.0 or newer required" > "/dev/stderr"; exit 1 } }
'
```

### 4. Export required environment variables

Agent steps expect the following variables in their environment:

| Variable | Source | Description |
|---|---|---|
| `GITHUB_TOKEN` | Secrets | Read/write token for GitHub API calls within the repo. |
| `APP_PRIVATE_KEY` | Secrets | Private key for the bot GitHub App; mints installation tokens for safe-output writes. |
| `COPILOT_GITHUB_TOKEN` | Secrets | Fine-grained PAT with Copilot Requests:Read; auth credential for `engine: copilot` inference calls. |

Set these in the workflow frontmatter or wrapper `secrets:` block, not
inside the agent prompt.

### 5. Failure behavior

If any setup step fails:

- Exit with a non-zero status code and a descriptive message to stderr.
- Do not attempt to run the agent step. A partially initialized environment
  produces unreliable agent output.
- The workflow surfaces the failure as a failed Actions check so the
  operator is alerted.
