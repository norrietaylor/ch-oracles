#!/usr/bin/env python3
r"""test-safe-output-allowlists.py — CI gate that cross-references each chore
workflow's `safe-outputs:` allowlist against the prose instructions in its
Markdown body.

The check protects against four classes of drift between the agent prose and
the gh-aw frontmatter that compiles into the lock file:

1. **writes-but-not-allowlisted** (label direction): prose instructs the
   chore to apply a label (e.g., `Labels: \`agent:autofix\``,
   `Apply \`needs-human\` label`) that is missing from the `safe-outputs`
   allowlist. At runtime gh-aw would reject the write, failing the chore
   silently mid-run.
2. **allowlisted-but-not-written** (label direction): the `safe-outputs`
   allowlist names a label that the workflow source prose never
   references. The allowlist entry is dead and masks a future bug (a
   follow-up PR that removes the only prose use of a label will not trip
   a check unless this direction is enforced).
3. **invoked-but-not-allowlisted** (action direction): prose (in the
   source body or any imported `shared/*.md` fragment) instructs the
   chore to emit a safe-output action (e.g., `create-issue`,
   `add-comment`, `push-to-pull-request-branch`) that is not declared in
   the `safe-outputs:` block. gh-aw will reject the emit at runtime.
4. **allowlisted-but-not-invoked** (action direction): `safe-outputs:`
   declares an action key that no prose (source body or imported
   fragments) references. The declared action is dead.

Scope:
  - Reads `workflows/*.md` sources (frontmatter + prose body). The action
    audit additionally walks the source's `imports:` list and concatenates
    the bodies of any local `shared/*.md` fragments (gh-aw inlines these
    at compile time, so a prose mention in a shared fragment is a real
    prose reference from the perspective of the runtime).
  - Missing `safe-outputs:` block in a workflow source is treated as a
    contract violation (the gate fails CI) rather than a silent skip.
  - Lock files in `.github/workflows/*.lock.yml` are derived artefacts;
    the `safe-outputs` block on the source is the contract being audited.
  - `wrappers/*.yml` are out of scope: those are thin pass-through callers
    with different semantics (see ADR 0006). They have a separate audit
    in `scripts/audit-wrapper-permissions.py`.

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


# Per-workflow exemptions for the action dead-entry direction
# (allowlisted-but-not-invoked). Same contract as DEAD_ENTRY_EXEMPTIONS:
# each entry is a real current-state mismatch on `main`; widening this
# dict requires a justifying note in the PR that introduces the exemption.
#
# worker-fix: declares `add-comment: max: 1` in `safe-outputs:` but the
# prose body never instructs the chore to post a comment (the chore only
# emits PRs and noops). Per issue #6, the worker is slated to migrate
# engine and this allowlist entry is expected to be removed as part of
# that work; carrying the exemption here keeps the gate green until then.
ACTION_DEAD_EXEMPTIONS: dict[str, set[str]] = {
    "worker-fix": {"add-comment"},
}


# Safe-output action keys whose label lists we audit. Each maps to the
# YAML sub-key under which labels live in the gh-aw schema.
LABEL_KEY_BY_ACTION: dict[str, str] = {
    "create-issue": "labels",
    "create-pull-request": "labels",
    "add-labels": "allowed",
}


# The complete set of safe-output action keys we audit. `github-app` is
# the credentials block, not a write action, and is excluded.
KNOWN_ACTION_KEYS: frozenset[str] = frozenset({
    "create-issue",
    "update-issue",
    "create-pull-request",
    "push-to-pull-request-branch",
    "add-comment",
    "add-labels",
    "reply-to-pull-request-review-comment",
})


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

# Backticked safe-output action token, used for action references.
BACKTICK_ACTION_PATTERN = re.compile(
    r"`(create-issue|update-issue|create-pull-request"
    r"|push-to-pull-request-branch|add-comment|add-labels"
    r"|reply-to-pull-request-review-comment)`"
)

# Natural-language anchors for actions whose prose typically avoids the
# raw action token. Each pattern, if it fires, counts as a prose
# invocation of the corresponding action key. Keep these narrow — false
# positives weaken the allowlisted-but-not-invoked direction.
ACTION_PROSE_ANCHORS: dict[str, re.Pattern[str]] = {
    # "Post a single comment", "Add a comment". Deliberately narrow: we
    # require the verb to land directly on `comment` (with at most an
    # article/quantifier in between) so phrasings like "Append <marker>
    # to a reply comment" — which describes modifying a review-comment
    # reply, not emitting add-comment — do not match.
    "add-comment": re.compile(
        r"\b(?:Post|Add)\s+(?:a|the|one|single|another)?\s*"
        r"(?:single|new)?\s*comment\b",
        re.IGNORECASE,
    ),
    # "Apply `<label>` label" / "Marking `<label>`" — both already imply
    # an add-labels emit. We also accept the literal "add labels" phrase.
    "add-labels": re.compile(
        r"\bApply\s+`(?:agent:[a-z][a-z0-9:_-]*|needs-human)`\s+label\b"
        r"|\bMarking\s+`(?:agent:[a-z][a-z0-9:_-]*|needs-human)`"
        r"|\badd\s+labels?\b",
        re.IGNORECASE,
    ),
    # "Reply to comments", "reply with a one-sentence explanation".
    "reply-to-pull-request-review-comment": re.compile(
        r"\b[Rr]eply\s+(?:to|with)\b", re.IGNORECASE
    ),
}


# Match a gh-aw `imports:` entry of the form
# `norrietaylor/ch-oracles/shared/<name>.md@<ref>` and capture <name>.md.
IMPORT_LOCAL_SHARED_PATTERN = re.compile(
    r"^.*?/shared/([A-Za-z0-9._-]+\.md)(?:@\S+)?$"
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


def imported_shared_bodies(frontmatter: dict, shared_dir: Path) -> str:
    """Concatenate the bodies of every locally-resolvable `shared/*.md`
    fragment listed in the workflow's `imports:` block.

    gh-aw inlines these fragments at compile time, so prose mentions in
    them count as workflow prose for the action audit. Imports that
    cannot be resolved to a local file (cross-repo references, or shared
    files that have been removed) are silently skipped — the action
    audit then sees them as missing prose, which is the conservative
    behaviour for the dead-entry direction.
    """
    imports = frontmatter.get("imports") or []
    if not isinstance(imports, list):
        return ""
    chunks: list[str] = []
    for entry in imports:
        if not isinstance(entry, str):
            continue
        m = IMPORT_LOCAL_SHARED_PATTERN.match(entry)
        if not m:
            continue
        target = shared_dir / m.group(1)
        if not target.is_file():
            continue
        try:
            chunks.append(target.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(chunks)


def extract_prose_actions(combined_prose: str) -> set[str]:
    """Return the set of safe-output action keys referenced in prose.

    `combined_prose` is the workflow source body concatenated with the
    bodies of any imported shared fragments (see `imported_shared_bodies`).
    A reference is one of:
      - a backticked action token (`create-issue`, `add-comment`, ...)
      - a natural-language anchor declared in `ACTION_PROSE_ANCHORS`.
    """
    actions: set[str] = set()
    for token in BACKTICK_ACTION_PATTERN.findall(combined_prose):
        actions.add(token)
    for action, pattern in ACTION_PROSE_ANCHORS.items():
        if pattern.search(combined_prose):
            actions.add(action)
    return actions


def check_workflow(source_path: Path, shared_dir: Path) -> list[str]:
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

    action_labels, declared_actions = extract_allowlist(frontmatter, name)
    all_allowed: set[str] = set()
    for labels in action_labels.values():
        all_allowed |= labels

    prose_writes = extract_prose_writes(body)
    prose_refs = extract_prose_references(body)

    # Action audit uses two different scopes:
    #   - Direction 1 (invoked-but-not-allowlisted): source body only.
    #     A backticked action token in the workflow's own prose is a
    #     direct, intentional signal that this chore emits that action.
    #     Importing a shared fragment that documents `create-issue` does
    #     NOT mean a particular chore emits it; the frontmatter decides.
    #   - Direction 2 (allowlisted-but-not-invoked): source body plus
    #     imported `shared/*.md` bodies. gh-aw inlines imports at compile
    #     time, so an action mention anywhere in the inlined material
    #     keeps the allowlist entry from being dead.
    source_actions = extract_prose_actions(body)
    combined_prose = body + "\n" + imported_shared_bodies(frontmatter, shared_dir)
    combined_actions = extract_prose_actions(combined_prose)

    violations: list[str] = []

    # Label direction 1: writes-but-not-allowlisted.
    for label in sorted(prose_writes):
        if label not in all_allowed:
            violations.append(
                f"{name}: writes-but-not-allowlisted '{label}' "
                f"(prose instructs a label write that no safe-outputs allowlist permits)"
            )

    # Label direction 2: allowlisted-but-not-written. Apply per-workflow
    # exemptions from DEAD_ENTRY_EXEMPTIONS for known taxonomic-tag cases.
    label_exempt = DEAD_ENTRY_EXEMPTIONS.get(name, set())
    for label in sorted(all_allowed):
        if label in label_exempt:
            continue
        if label not in prose_refs and label not in prose_writes:
            violations.append(
                f"{name}: allowlisted-but-not-written '{label}' "
                f"(safe-outputs permits the label but the prose never references it)"
            )

    # Action direction 1: invoked-but-not-allowlisted. Source-body prose
    # names an action key that the safe-outputs block does not declare;
    # gh-aw would reject the emit at runtime.
    for action in sorted(source_actions):
        if action not in declared_actions:
            violations.append(
                f"{name}: invoked-but-not-allowlisted '{action}' "
                f"(prose references a safe-output action not declared in safe-outputs:)"
            )

    # Action direction 2: allowlisted-but-not-invoked. safe-outputs:
    # declares an action that neither the source body nor any imported
    # shared fragment references. Restrict the audit to
    # `KNOWN_ACTION_KEYS` so we do not false-flag forward-compat keys we
    # have not yet taught the prose-action extractor about.
    action_exempt = ACTION_DEAD_EXEMPTIONS.get(name, set())
    for action in sorted(declared_actions):
        if action not in KNOWN_ACTION_KEYS:
            continue
        if action in action_exempt:
            continue
        if action not in combined_actions:
            violations.append(
                f"{name}: allowlisted-but-not-invoked '{action}' "
                f"(safe-outputs declares the action but no prose references it)"
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
    p.add_argument(
        "--shared-dir",
        default="shared",
        help="directory containing imported shared/*.md fragments",
    )
    args = p.parse_args()

    if args.sources:
        sources = [Path(s) for s in args.sources]
    else:
        sources = sorted(Path(args.workflows_dir).glob("*.md"))

    if not sources:
        sys.stderr.write(f"no workflow sources found in {args.workflows_dir}\n")
        return 2

    shared_dir = Path(args.shared_dir)

    all_violations: list[str] = []
    checked = 0
    for src in sources:
        if not src.exists():
            sys.stderr.write(f"warn: {src} does not exist; skipping\n")
            continue
        # A workflow source missing the `safe-outputs:` block is treated
        # as a contract violation rather than silently skipped: every
        # chore in this repo emits at least one safe-output, so an
        # accidental removal of the block (e.g., during a refactor) must
        # fail CI rather than slip through.
        text = src.read_text(encoding="utf-8")
        checked += 1
        if "safe-outputs:" not in text:
            all_violations.append(
                f"{src.stem}: missing safe-outputs block "
                f"(every chore workflow must declare a safe-outputs: contract)"
            )
            continue
        all_violations.extend(check_workflow(src, shared_dir))

    if all_violations:
        sys.stderr.write("safe-output allowlist contract violations:\n")
        for v in all_violations:
            sys.stderr.write(f"  - {v}\n")
        return 1

    print(f"checked {checked} workflow sources; safe-output allowlists match prose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
