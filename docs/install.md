# Install

## One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/gominimal/ch-oracles/main/scripts/quick-setup.sh \
  | bash -s -- --suite oracles
```

This installs:

- A wrapper YAML for every chore in
  `.github/workflows/<chore>.yml`. Each wrapper calls the corresponding
  hosted `.lock.yml` from `gominimal/ch-oracles`.
- `.github/AGENTS.md` with the agent contract.
- `.github/labels.yml` with the ch-oracles label taxonomy (merged with
  any existing `labels.yml`).
- `.github/ISSUE_TEMPLATE/{bug,feature,chore}.md`.
- `.github/copilot-instructions.md`.

## Flags

| Flag | Default | Description |
|---|---|---|
| `--suite oracles` | required | Install all ch-oracles wrappers. |
| `--languages rust,python,...` | auto-detect | Restrict lint + dep-bump wrappers to declared languages. |
| `--with-workers` | off | Install `worker-fix`, `worker-iterate`, `pr-conflict-resolver`. |
| `--no-templates` | off | Skip AGENTS.md and labels.yml installation. |
| `--source-ref <ref>` | `main` | Pin a specific ch-oracles release tag or SHA in wrappers. |
| `--update` | off | Refresh existing install; preserve user-edited sections. |
| `--dry-run` | off | Preview actions; no writes. |

## Auto-detect

When `--languages` is omitted, the script scans the consumer repo's root:

| Manifest / file pattern | Language |
|---|---|
| `Cargo.toml` | rust |
| `pyproject.toml` | python |
| `go.mod` | go |
| `*.toml` outside of `Cargo.toml` | toml |
| `*.ncl` | ncl |

A repo matching multiple patterns is polyglot; every matching language's
lint and dep-bump wrappers install.

## Required secrets

The consumer repo needs:

| Secret | Used by | How to provision |
|---|---|---|
| `APP_PRIVATE_KEY` | All workflows (safe-output writes) | GitHub App private key (PEM) |
| `COPILOT_GITHUB_TOKEN` | All workflows (chores + workers) | Fine-grained PAT with `Copilot Requests: Read` |

Every workflow in the suite runs on `engine: copilot`; a single inference
secret backs the entire suite. See
[ADR 0008](https://github.com/gominimal/ch-oracles/blob/main/decisions/0008-single-engine-copilot.md).

Set via repository or organization secrets:

```bash
gh secret set APP_PRIVATE_KEY --body @path/to/private-key.pem
gh secret set COPILOT_GITHUB_TOKEN --body "$(read -s tok && echo "$tok")"
```

## Required variables

| Variable | Used by | Description |
|---|---|---|
| `APP_ID` | All chores | GitHub App ID for the bot identity |
| `CH_ORACLES_LANGUAGE` | Workers | Optional. Pin the consumer language to one of `rust`, `python`, `go`, `toml`, `ncl`, or `polyglot`. |

## Sync labels

After install:

```bash
gh label sync -f .github/labels.yml
```

(Requires `github/gh-label` or `gh-actions/labeler`. See
[github.com/EndBug/label-sync](https://github.com/EndBug/label-sync) for
an Action-based alternative.)

## Upgrade

```bash
curl -fsSL https://raw.githubusercontent.com/gominimal/ch-oracles/main/scripts/quick-setup.sh \
  | bash -s -- --suite oracles --update --source-ref v0.2.0
```

`--update` refreshes wrappers, AGENTS.md non-override sections, and label
definitions. The `## Build Commands (ch-oracles override)` section of
AGENTS.md is preserved across runs.

## Co-installation with spectacles

Install spectacles first, then ch-oracles (order does not matter):

```bash
curl -fsSL https://raw.githubusercontent.com/gominimal/spectacles/main/scripts/quick-setup.sh | bash -s -- --suite sdd
curl -fsSL https://raw.githubusercontent.com/gominimal/ch-oracles/main/scripts/quick-setup.sh | bash -s -- --suite oracles
```

`AGENTS.md` and `labels.yml` updates are additive; each suite owns its own
section markers and label namespaces. See
[Coexistence with spectacles](coexistence-with-spectacles.md).
