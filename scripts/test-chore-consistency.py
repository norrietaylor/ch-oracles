#!/usr/bin/env python3
"""test-chore-consistency.py — CI gate that asserts every chore is consistent
across its three artifacts and the AGENTS.md catalogue.

Per issue #2, every chore in ch-oracles ships three lock-step artifacts:

  - `workflows/<name>.md`            (gh-aw source; authoritative)
  - `.github/workflows/<name>.lock.yml`  (compiled artifact)
  - `wrappers/<name>.yml`            (thin consumer wrapper)

Plus a row in `templates/.github/AGENTS.md`'s "Active chore workflows" table.

A drift in any of the four surfaces is a silent footgun: the wrapper might
invoke a nonexistent lock file, the lock file might require a secret the
wrapper never forwards, or the catalogue row may point at a chore that no
longer ships. This script asserts:

  1. The four basename sets are equal (uniform set membership).
  2. Each wrapper's `jobs.*.uses:` resolves to a real lock file matching the
     wrapper's basename.
  3. Each `required: true` secret declared in the lock file's
     `on.workflow_call.secrets` schema is forwarded by the wrapper's
     `jobs.*.secrets:` block (or the wrapper uses `secrets: inherit`).

Exit code 0 if all gates pass; 1 with a one-line-per-finding diagnostic
otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML required. install with: pip install pyyaml\n")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent

WORKFLOWS_DIR = REPO_ROOT / "workflows"
WRAPPERS_DIR = REPO_ROOT / "wrappers"
LOCKS_DIR = REPO_ROOT / ".github" / "workflows"
AGENTS_MD = REPO_ROOT / "templates" / ".github" / "AGENTS.md"

# Owner/repo segment of the expected `uses:` value. Wrappers may pin to a tag,
# SHA, or the {{SOURCE_REF}} placeholder; the ref itself is policed by the
# fragment-sync policy (ADR 0007), so we only assert the resource path.
USES_PREFIX = "norrietaylor/ch-oracles/.github/workflows/"
USES_SUFFIX = ".lock.yml"


# ──────────────────────────────────────────────────────────────────────────
# YAML helpers
# ──────────────────────────────────────────────────────────────────────────


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def get_on_block(doc: dict) -> dict:
    """Return the workflow's `on:` block.

    PyYAML's safe_load resolves an unquoted `on:` key to the boolean True
    (YAML 1.1 spec). Quoted `"on":` stays a string. Handle both.
    """
    if "on" in doc:
        block = doc["on"]
    elif True in doc:
        block = doc[True]
    else:
        return {}
    return block if isinstance(block, dict) else {}


def collect_uses_jobs(jobs: dict) -> list[tuple[str, str]]:
    """Return [(job_name, uses_value), ...] for every job declaring `uses:`."""
    out: list[tuple[str, str]] = []
    if not isinstance(jobs, dict):
        return out
    for name, job in jobs.items():
        if isinstance(job, dict) and isinstance(job.get("uses"), str):
            out.append((name, job["uses"]))
    return out


def collect_secrets_blocks(jobs: dict) -> list[tuple[str, object]]:
    """Return [(job_name, secrets_block), ...] for every job declaring `secrets:`.

    The block is either the string 'inherit' or a mapping of secret keys to
    expressions.
    """
    out: list[tuple[str, object]] = []
    if not isinstance(jobs, dict):
        return out
    for name, job in jobs.items():
        if isinstance(job, dict) and "secrets" in job:
            out.append((name, job["secrets"]))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Set-builders for each artifact surface
# ──────────────────────────────────────────────────────────────────────────


def workflow_md_set() -> set[str]:
    return {p.stem for p in WORKFLOWS_DIR.glob("*.md")}


def wrapper_set() -> set[str]:
    return {p.stem for p in WRAPPERS_DIR.glob("*.yml")}


def lock_set() -> set[str]:
    """Strip the `.lock` suffix from `<name>.lock.yml` files."""
    out: set[str] = set()
    for p in LOCKS_DIR.glob("*.lock.yml"):
        # p.stem == "<name>.lock" because .yml is the only "extension".
        if p.stem.endswith(".lock"):
            out.add(p.stem[: -len(".lock")])
    return out


# Table-row parsing.
#
# The AGENTS.md table uses literal chore names in backticks for some rows
# (`docs-patrol`, `worker-fix`) and parameterised stems for the per-language
# rows (`chore-style-<lang>`, `trivial-dep-bump-<lang>`). We expand any cell
# containing a `<...>` placeholder against the actual wrapper set so the
# catalogue row covers every materialised chore.

_TABLE_HEADER_RE = re.compile(r"^\s*\|\s*Workflow\s*\|", re.IGNORECASE)
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*`([^`|]+)`")  # first cell, backticked


def agents_md_table_set(realised: set[str]) -> set[str]:
    """Parse the 'Active chore workflows' table and expand `<lang>` rows.

    Returns the set of fully expanded chore names listed in the table. Rows
    whose first cell is not a backticked identifier are skipped (e.g. the
    separator row).
    """
    if not AGENTS_MD.exists():
        return set()

    out: set[str] = set()
    in_active_section = False
    in_table = False

    for raw in AGENTS_MD.read_text().splitlines():
        line = raw.rstrip()
        # Section gate: only consume the table immediately after the
        # "Active chore workflows" heading.
        if line.startswith("## "):
            in_active_section = line.strip("# ").strip().lower() == "active chore workflows"
            in_table = False
            continue
        if not in_active_section:
            continue

        if _TABLE_HEADER_RE.match(line):
            in_table = True
            continue
        if in_table and line.lstrip().startswith("|---"):
            continue
        if in_table and not line.lstrip().startswith("|"):
            # Blank line or following prose ends the table.
            in_table = False
            continue

        if not in_table:
            continue

        m = _TABLE_ROW_RE.match(line)
        if not m:
            continue
        stem = m.group(1).strip()

        if "<" in stem and ">" in stem:
            # Expand template against the realised wrapper set.
            #
            #   "chore-style-<lang>"  ->  regex "^chore-style-[^-]+$"
            #   "trivial-dep-bump-<lang>"  ->  regex "^trivial-dep-bump-[^-]+$"
            #
            # `[^-]+` is loose-on-purpose: the spec only constrains shape, not
            # the enumerated language list. Any matching realised wrapper
            # counts as a satisfied row. re.escape() turns the `<` and `>`
            # placeholders into `\<` and `\>`, so we substitute the regex
            # class into the escaped form directly.
            pattern = re.sub(r"<[^>]+>", "[^-]+", "^" + re.escape(stem) + "$")
            rx = re.compile(pattern)
            matched = {n for n in realised if rx.match(n)}
            if matched:
                out.update(matched)
            else:
                # Keep the placeholder in the set so the equality diff names
                # it as the offender.
                out.add(stem)
        else:
            out.add(stem)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Per-wrapper validation
# ──────────────────────────────────────────────────────────────────────────


def parse_uses(uses: str) -> str | None:
    """Return the `<name>` of the lock file targeted by a `uses:` value.

    Expected shape: `norrietaylor/ch-oracles/.github/workflows/<name>.lock.yml@<ref>`.
    Returns None if the shape does not match.
    """
    if not uses.startswith(USES_PREFIX):
        return None
    tail = uses[len(USES_PREFIX) :]
    # Split off the ref.
    if "@" not in tail:
        return None
    path_part, _ref = tail.rsplit("@", 1)
    if not path_part.endswith(USES_SUFFIX):
        return None
    return path_part[: -len(USES_SUFFIX)]


def required_secrets(lock_doc: dict) -> set[str]:
    on_block = get_on_block(lock_doc)
    wc = on_block.get("workflow_call") or {}
    if not isinstance(wc, dict):
        return set()
    secrets = wc.get("secrets") or {}
    if not isinstance(secrets, dict):
        return set()
    out: set[str] = set()
    for key, spec in secrets.items():
        if isinstance(spec, dict) and spec.get("required") is True:
            out.add(str(key))
    return out


def wrapper_forwarded_secrets(wrapper_doc: dict) -> tuple[set[str], bool]:
    """Return (forwarded_keys, inherits_all).

    `secrets: inherit` on any job is treated as satisfying every required
    secret in the corresponding lock contract.
    """
    forwarded: set[str] = set()
    inherits_all = False
    jobs = wrapper_doc.get("jobs") or {}
    for _name, block in collect_secrets_blocks(jobs):
        if isinstance(block, str) and block.strip().lower() == "inherit":
            inherits_all = True
        elif isinstance(block, dict):
            forwarded.update(str(k) for k in block.keys())
    return forwarded, inherits_all


def validate_wrapper(wrapper_path: Path) -> list[str]:
    findings: list[str] = []
    rel = wrapper_path.relative_to(REPO_ROOT)
    name = wrapper_path.stem

    try:
        wrapper = load_yaml(wrapper_path)
    except yaml.YAMLError as e:  # pragma: no cover — defensive
        return [f"{rel}: unparseable YAML — {e}"]

    jobs = wrapper.get("jobs") or {}
    uses_jobs = collect_uses_jobs(jobs)
    if not uses_jobs:
        findings.append(f"{rel}: no job declares `uses:` — wrapper must call a hosted lock file")
        return findings

    # Allow secondary helper jobs (pr-conflict-resolver has a `detect:` job
    # with no `uses:`). Locate the call-job — the one whose `uses:` points
    # at our owner/repo.
    target_jobs = [
        (jn, u) for jn, u in uses_jobs if u.startswith(USES_PREFIX)
    ]
    if not target_jobs:
        findings.append(
            f"{rel}: no job uses norrietaylor/ch-oracles/.github/workflows/* — wrapper does not call a ch-oracles lock"
        )
        return findings
    if len(target_jobs) > 1:
        findings.append(
            f"{rel}: multiple jobs ({', '.join(j for j, _ in target_jobs)}) call ch-oracles locks — only one expected"
        )

    _job_name, uses = target_jobs[0]
    parsed = parse_uses(uses)
    if parsed is None:
        findings.append(
            f"{rel}: malformed `uses:` value — expected "
            f"`norrietaylor/ch-oracles/.github/workflows/<name>.lock.yml@<ref>`, got `{uses}`"
        )
        return findings
    if parsed != name:
        findings.append(
            f"{rel}: `uses:` targets `{parsed}.lock.yml` but wrapper basename is `{name}` (mismatch)"
        )

    lock_path = LOCKS_DIR / f"{parsed}.lock.yml"
    if not lock_path.exists():
        findings.append(
            f"{rel}: orphan — `uses:` points at `{parsed}.lock.yml` but no such lock file exists"
        )
        return findings

    try:
        lock = load_yaml(lock_path)
    except yaml.YAMLError as e:  # pragma: no cover — defensive
        return findings + [f"{lock_path.relative_to(REPO_ROOT)}: unparseable YAML — {e}"]

    required = required_secrets(lock)
    forwarded, inherits_all = wrapper_forwarded_secrets(wrapper)
    if inherits_all:
        return findings
    missing = sorted(required - forwarded)
    for sec in missing:
        findings.append(
            f"{rel}: missing required secret `{sec}` "
            f"(declared `required: true` in {lock_path.relative_to(REPO_ROOT)})"
        )
    return findings


# ──────────────────────────────────────────────────────────────────────────
# Set-equality reporting
# ──────────────────────────────────────────────────────────────────────────


def diff_sets(
    sources: set[str],
    wrappers: set[str],
    locks: set[str],
    agents: set[str],
) -> list[str]:
    """Produce one finding per name that is missing from any surface."""
    findings: list[str] = []
    universe = sources | wrappers | locks | agents
    for name in sorted(universe):
        missing_from: list[str] = []
        if name not in sources:
            missing_from.append("workflows/<name>.md")
        if name not in wrappers:
            missing_from.append("wrappers/<name>.yml")
        if name not in locks:
            missing_from.append(".github/workflows/<name>.lock.yml")
        if name not in agents:
            missing_from.append("templates/.github/AGENTS.md table")
        if missing_from:
            findings.append(
                f"chore `{name}` missing from: {', '.join(missing_from)}"
            )
    return findings


# ──────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────


def main() -> int:
    if not WORKFLOWS_DIR.is_dir():
        sys.stderr.write(f"error: {WORKFLOWS_DIR} not found — run from repo root\n")
        return 2

    sources = workflow_md_set()
    wrappers = wrapper_set()
    locks = lock_set()
    realised = sources | wrappers | locks
    agents = agents_md_table_set(realised)

    findings: list[str] = []
    findings.extend(diff_sets(sources, wrappers, locks, agents))
    for wrapper_path in sorted(WRAPPERS_DIR.glob("*.yml")):
        findings.extend(validate_wrapper(wrapper_path))

    if findings:
        sys.stderr.write("chore-consistency: findings\n")
        for f in findings:
            sys.stderr.write(f"  - {f}\n")
        return 1

    total = len(sources)
    print(f"chore-consistency: OK — {total} chores consistent across all four surfaces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
