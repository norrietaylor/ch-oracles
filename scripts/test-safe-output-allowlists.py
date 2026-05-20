#!/usr/bin/env python3
r"""test-safe-output-allowlists.py — CI gate that cross-references each chore
workflow's `safe-outputs:` allowlist against the prose instructions in its
Markdown body.

The check protects against two classes of drift between the agent prose and
the gh-aw frontmatter that compiles into the lock file:

1. **writes-but-not-allowlisted**: prose instructs the chore to apply a
   label (e.g., `Labels: \`agent:autofix\``, `Apply \`needs-human\` label`)
   that is missing from the `safe-outputs` allowlist. At runtime gh-aw
   would reject the write, failing the chore silently mid-run.
2. **allowlisted-but-not-written**: the `safe-outputs` allowlist names a
   label that the prose never references. The allowlist entry is dead and
   masks a future bug (a follow-up PR that removes the only prose use of a
   label will not trip a check unless this direction is enforced).

Scope:
  - Reads `workflows/*.md` sources (frontmatter + prose body).
  - Lock files in `.github/workflows/*.lock.yml` are derived artefacts; the
    `safe-outputs` block on the source is the contract being audited.
  - `wrappers/*.yml` are out of scope: those are thin pass-through callers
    with different semantics (see ADR 0006). They have a separate audit in
    `scripts/audit-wrapper-permissions.py`.

Usage:
    python scripts/test-safe-output-allowlists.py
    python scripts/test-safe-output-allowlists.py workflows/chore-style-rust.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML required. install with: pip install pyyaml\n")
    sys.exit(2)


# Calibration allowlists: tightly-scoped per-workflow exemptions for the
# dead-entry direction (allowlisted-but-not-written). Each entry is a real
# current-state mismatch on `main` documented in PR #1; widening this dict
# requires a justifying note in the PR that introduces the exemption.
#
# trivial-dep-bump-{rust,python,go}: declare `agent:dep-drift` on
# create-pull-request because dep-bump PRs are part of the dep-drift workflow
# class (the auto-merge label is the active write; agent:dep-drift is a
# taxonomic tag auto-applied by gh-aw). The prose talks about auto-merge but
# not the taxonomic tag.
#
# trivial-dep-bump-go: additionally exempts `agent:auto-merge` because the
# Go variant's prose only references auto-merge as the behavior noun
# ("auto-merge enabled"), not the literal label name, while the rust/python
# variants do say "label it `agent:auto-merge`" in prose. Behavioral parity
# bug; not a contract bug.
DEAD_ENTRY_EXEMPTIONS: dict[str, set[str]] = {
    "trivial-dep-bump-rust": {"agent:dep-drift"},
    "trivial-dep-bump-python": {"agent:dep-drift"},
    "trivial-dep-bump-go": {"agent:dep-drift", "agent:auto-merge"},
}


# Safe-output action keys whose label lists we audit. Each maps to the
# YAML sub-key under which labels live in the gh-aw schema.
LABEL_KEY_BY_ACTION: dict[str, str] = {
    "create-issue": "labels",
    "create-pull-request": "labels",
    "add-labels": "allowed",
}


FRONTMATTER_DELIM = "---"

# Label tokens we audit: agent:* and the literal needs-human.
LABEL_PATTERN = re.compile(r"\b(agent:[a-z][a-z0-9:_-]*|needs-human)\b")

# Backtick-quoted label, used for prose mentions.
BACKTICK_LABEL_PATTERN = re.compile(
    r"`(agent:[a-z][a-z0-9:_-]*|needs-human)`"
)

# A "Labels:" line under a procedure step:
#     - Labels: `agent:lint:rust`, `agent:autofix`.
LABELS_LINE_PATTERN = re.compile(r"^\s*[-*]?\s*Labels:\s*(.+)$")

# "Apply `<label>` label" — explicit positive instruction.
APPLY_LABEL_PATTERN = re.compile(
    r"\bApply\s+`(agent:[a-z][a-z0-9:_-]*|needs-human)`\s+label\b"
)

# "Marking `<label>`" — also a positive instruction.
MARKING_LABEL_PATTERN = re.compile(
    r"\bMarking\s+`(agent:[a-z][a-z0-9:_-]*|needs-human)`"
)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_yaml, body) from a Markdown file with `---` fences.

    Raises ValueError if the file does not start with a frontmatter fence.
    """
    if not text.startswith(FRONTMATTER_DELIM):
        raise ValueError("file does not begin with --- frontmatter fence")
    # Skip the opening fence line.
    rest = text[len(FRONTMATTER_DELIM):].lstrip("\n")
    end = rest.find("\n" + FRONTMATTER_DELIM)
    if end < 0:
        raise ValueError("frontmatter fence not closed")
    fm = rest[:end]
    body = rest[end + len("\n" + FRONTMATTER_DELIM):]
    # Trim leading newlines on the body.
    body = body.lstrip("\n")
    return fm, body


def extract_allowlist(frontmatter: dict, workflow_name: str) -> tuple[dict[str, set[str]], set[str]]:
    """Return ({action -> set(labels)}, set(declared_action_keys)).

    Walks `safe-outputs:` and pulls per-action label lists. Also returns the
    set of declared safe-output action keys (e.g. {create-issue,
    update-issue, create-pull-request, add-labels, add-comment,
    push-to-pull-request-branch, reply-to-pull-request-review-comment,
    update-issue}). The action-key set powers the action-level audit.
    """
    safe_outputs = frontmatter.get("safe-outputs") or {}
    if not isinstance(safe_outputs, dict):
        return {}, set()

    action_labels: dict[str, set[str]] = {}
    actions: set[str] = set()

    for action_key, config in safe_outputs.items():
        # Skip the github-app credentials block; it is not a write action.
        if action_key == "github-app":
            continue
        actions.add(action_key)
        if not isinstance(config, dict):
            continue
        label_key = LABEL_KEY_BY_ACTION.get(action_key)
        if not label_key:
            continue
        labels = config.get(label_key)
        if not isinstance(labels, list):
            continue
        action_labels[action_key] = {str(lbl) for lbl in labels if isinstance(lbl, str)}

    return action_labels, actions


# Section headings whose contents are negative instructions (do-NOT
# directives). Lines under such headings must not contribute to the
# "writes" set; they may still contribute to the "references" set for the
# dead-entry direction (a label mentioned only in a "do not" block is
# still a known reference, not a dead entry).
NEGATIVE_SECTION_HEADINGS = (
    "what you must not do",
    "must not do",
    "do not",
    "constraints you must obey",
    "constraints",
)


def iter_body_lines_with_section(body: str):
    """Yield (line, current_section_heading_lower) for each line in body."""
    current = ""
    for raw in body.splitlines():
        stripped = raw.strip()
        # Match Markdown section headings: ##, ###, etc.
        m = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if m:
            current = m.group(1).strip().lower()
        yield raw, current


def is_negative_section(section: str) -> bool:
    return any(needle in section for needle in NEGATIVE_SECTION_HEADINGS)


def extract_prose_writes(body: str) -> set[str]:
    """Return the set of labels the prose instructs the chore to write.

    Scans only positive-instruction contexts: skips lines under
    "What you must not do"-style headings.
    """
    writes: set[str] = set()
    for line, section in iter_body_lines_with_section(body):
        if is_negative_section(section):
            continue
        # Strip any leading list bullet for `Labels:` matching.
        m = LABELS_LINE_PATTERN.match(line)
        if m:
            for token in BACKTICK_LABEL_PATTERN.findall(m.group(1)):
                writes.add(token)
            # Also tolerate non-backticked listings in case prose drifts.
            for token in LABEL_PATTERN.findall(m.group(1)):
                writes.add(token)
        for token in APPLY_LABEL_PATTERN.findall(line):
            writes.add(token)
        for token in MARKING_LABEL_PATTERN.findall(line):
            writes.add(token)
    return writes


def extract_prose_references(body: str) -> set[str]:
    """Return every label token referenced anywhere in the prose body.

    This is the broader set used to validate that no allowlist entry is
    dead; even a backtick mention in a do-not block keeps the entry live.
    """
    refs: set[str] = set()
    for token in BACKTICK_LABEL_PATTERN.findall(body):
        refs.add(token)
    return refs


def check_workflow(source_path: Path) -> list[str]:
    """Return a list of one-line violation messages; empty means OK."""
    name = source_path.stem
    text = source_path.read_text(encoding="utf-8")
    try:
        fm_text, body = split_frontmatter(text)
    except ValueError as exc:
        return [f"{name}: cannot parse frontmatter ({exc})"]

    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return [f"{name}: invalid YAML frontmatter ({exc})"]

    action_labels, _actions = extract_allowlist(frontmatter, name)
    all_allowed: set[str] = set()
    for labels in action_labels.values():
        all_allowed |= labels

    prose_writes = extract_prose_writes(body)
    prose_refs = extract_prose_references(body)

    violations: list[str] = []

    # Direction 1: writes-but-not-allowlisted.
    for label in sorted(prose_writes):
        if label not in all_allowed:
            violations.append(
                f"{name}: writes-but-not-allowlisted '{label}' "
                f"(prose instructs a label write that no safe-outputs allowlist permits)"
            )

    # Direction 2: allowlisted-but-not-written. Apply per-workflow
    # exemptions from DEAD_ENTRY_EXEMPTIONS for known taxonomic-tag cases.
    exempt = DEAD_ENTRY_EXEMPTIONS.get(name, set())
    for label in sorted(all_allowed):
        if label in exempt:
            continue
        if label not in prose_refs and label not in prose_writes:
            violations.append(
                f"{name}: allowlisted-but-not-written '{label}' "
                f"(safe-outputs permits the label but the prose never references it)"
            )

    return violations


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("sources", nargs="*", help="workflow Markdown sources to check")
    p.add_argument(
        "--workflows-dir",
        default="workflows",
        help="directory containing *.md workflow sources",
    )
    args = p.parse_args()

    if args.sources:
        sources = [Path(s) for s in args.sources]
    else:
        sources = sorted(Path(args.workflows_dir).glob("*.md"))

    if not sources:
        sys.stderr.write(f"no workflow sources found in {args.workflows_dir}\n")
        return 2

    all_violations: list[str] = []
    checked = 0
    for src in sources:
        if not src.exists():
            sys.stderr.write(f"warn: {src} does not exist; skipping\n")
            continue
        # Skip sources without a `safe-outputs:` block (none currently, but
        # be defensive for non-chore workflow markdown that might land here).
        text = src.read_text(encoding="utf-8")
        if "safe-outputs:" not in text:
            continue
        all_violations.extend(check_workflow(src))
        checked += 1

    if all_violations:
        sys.stderr.write("safe-output allowlist contract violations:\n")
        for v in all_violations:
            sys.stderr.write(f"  - {v}\n")
        return 1

    print(f"checked {checked} workflow sources; safe-output allowlists match prose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
