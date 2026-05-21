#!/usr/bin/env python3
"""Static validator for the ch-oracles label taxonomy.

This script enforces the invariants documented in `templates/.github/AGENTS.md`
and ADRs 0001 (not-gating) and 0003 (spectacles coexistence). It cross-checks
three sources:

  1. `templates/.github/labels.yml`       — the label inventory.
  2. `scripts/label-classes.yml`          — the classification config.
  3. `workflows/*.md` frontmatter         — the actual label writers
                                            declared in safe-outputs blocks.

It asserts:

  * Every label in the inventory is classified in the config (and vice versa).
  * Every `chore-output` label has exactly one issue-side writer, matching
    the configured `writer`.
  * Every `pr-marker` label has at least one PR-side writer, and every such
    writer matches the configured glob.
  * The set of chores that write `needs-human` matches the configured
    `handoff_writers` set. (AGENTS.md does not yet enumerate emitters in a
    machine-readable table; per issue #3 we declare the expected set in the
    config so additions on either side force a coordinated edit.)
  * The set of chores that consume `needs-human` — detected as a literal
    string match in the workflow body — matches the configured
    `handoff_consumers` set.

Writers are split by output channel because the same label may legally be
applied to an issue by chore A and to a PR by chore B (e.g. `agent:dep-drift`
is the issue classifier emitted by `dependency-review` and is also stamped
onto auto-merge PRs by `trivial-dep-bump-*`). Only same-channel collisions
violate uniqueness.

Exit code:
  0  All assertions passed.
  1  At least one assertion failed (failures printed to stderr).
"""

from __future__ import annotations

import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_FILE = REPO_ROOT / "templates" / ".github" / "labels.yml"
CLASSES_FILE = REPO_ROOT / "scripts" / "label-classes.yml"
WORKFLOWS_DIR = REPO_ROOT / "workflows"

# safe-outputs sub-keys that write labels onto an *issue*.
ISSUE_OUTPUT_KEYS = ("create-issue", "update-issue", "add-labels")
# safe-outputs sub-keys that write labels onto a *pull request*.
PR_OUTPUT_KEYS = ("create-pull-request",)

VALID_CLASSES = {"chore-output", "pr-marker", "handoff", "triage"}


@dataclass
class LabelWriters:
    """Track which workflows write a label, split by output channel."""

    issue: set[str] = field(default_factory=set)
    pr: set[str] = field(default_factory=set)

    def any(self) -> set[str]:
        return self.issue | self.pr


def _read_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_label_inventory() -> set[str]:
    """Return the set of label names declared in templates/.github/labels.yml."""
    data = _read_yaml(LABELS_FILE)
    if not isinstance(data, list):
        raise SystemExit(f"{LABELS_FILE}: expected a top-level list of labels")
    names: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict) or "name" not in entry:
            raise SystemExit(f"{LABELS_FILE}: malformed entry: {entry!r}")
        names.add(entry["name"])
    return names


def load_classification() -> dict:
    """Return the parsed label-classes.yml content (raw dict)."""
    data = _read_yaml(CLASSES_FILE)
    if not isinstance(data, dict) or "labels" not in data:
        raise SystemExit(f"{CLASSES_FILE}: expected a top-level mapping with `labels:`")
    return data


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(path: Path) -> dict:
    """Extract the YAML frontmatter from a `workflows/*.md` file."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.search(text)
    if not match:
        return {}
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SystemExit(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    return loaded if isinstance(loaded, dict) else {}


def _extract_labels_from_output(node: object) -> list[str]:
    """Pull a `labels:` or `allowed:` list out of a safe-outputs sub-node."""
    if not isinstance(node, dict):
        return []
    out: list[str] = []
    # Standard label list under safe-outputs.<channel>.labels
    labels = node.get("labels")
    if isinstance(labels, list):
        out.extend(str(x) for x in labels)
    # `add-labels` uses `allowed:` to whitelist what may be applied.
    allowed = node.get("allowed")
    if isinstance(allowed, list):
        out.extend(str(x) for x in allowed)
    return out


def collect_writers(workflow_paths: Iterable[Path]) -> dict[str, LabelWriters]:
    """Return {label_name: LabelWriters} aggregated across every workflow."""
    writers: dict[str, LabelWriters] = {}
    for path in workflow_paths:
        wf_name = path.stem
        fm = parse_frontmatter(path)
        safe = fm.get("safe-outputs")
        if not isinstance(safe, dict):
            continue
        for key in ISSUE_OUTPUT_KEYS:
            for lbl in _extract_labels_from_output(safe.get(key)):
                writers.setdefault(lbl, LabelWriters()).issue.add(wf_name)
        for key in PR_OUTPUT_KEYS:
            for lbl in _extract_labels_from_output(safe.get(key)):
                writers.setdefault(lbl, LabelWriters()).pr.add(wf_name)
    return writers


# Literal-text search for `needs-human` (and any other handoff label) inside
# the workflow body — used to detect consumers (which read/honor the label
# without writing it via safe-outputs).
def collect_handoff_consumers(workflow_paths: Iterable[Path], label: str) -> set[str]:
    consumers: set[str] = set()
    needle = label
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        # Strip the frontmatter so writes (declared there) don't auto-classify
        # the workflow as a consumer.
        body = FRONTMATTER_RE.sub("", text, count=1)
        if needle in body:
            consumers.add(path.stem)
    return consumers


def main() -> int:
    errors: list[str] = []

    inventory = load_label_inventory()
    config = load_classification()
    classes = config.get("labels", {})
    if not isinstance(classes, dict):
        raise SystemExit(f"{CLASSES_FILE}: `labels:` must be a mapping")

    # 1. Every inventory label must be classified.
    for lbl in sorted(inventory):
        if lbl not in classes:
            errors.append(f"unknown label class: {lbl}")

    # 2. Every classified label must exist in the inventory (catches drift in
    #    the other direction: stale config entries for removed labels).
    for lbl in sorted(classes):
        if lbl not in inventory:
            errors.append(
                f"label-classes.yml lists `{lbl}` but it is not in "
                f"templates/.github/labels.yml"
            )

    # Validate class values.
    for lbl, spec in classes.items():
        if not isinstance(spec, dict) or "class" not in spec:
            errors.append(f"{lbl}: classification entry must have a `class:` field")
            continue
        if spec["class"] not in VALID_CLASSES:
            errors.append(
                f"{lbl}: invalid class `{spec['class']}` "
                f"(valid: {sorted(VALID_CLASSES)})"
            )

    # Collect writers from workflow sources.
    workflow_paths = sorted(WORKFLOWS_DIR.glob("*.md"))
    if not workflow_paths:
        raise SystemExit(f"no workflow sources found under {WORKFLOWS_DIR}")
    writers = collect_writers(workflow_paths)

    # 3. chore-output: exactly one issue-side writer, matching `writer`.
    for lbl, spec in classes.items():
        if not isinstance(spec, dict) or spec.get("class") != "chore-output":
            continue
        expected = spec.get("writer")
        if not expected:
            errors.append(f"{lbl}: chore-output entry missing `writer:` field")
            continue
        issue_writers = writers.get(lbl, LabelWriters()).issue
        if not issue_writers:
            errors.append(
                f"{lbl} has no writer: declared as chore-output with "
                f"writer=`{expected}` but no workflow writes it on issues"
            )
            continue
        if len(issue_writers) > 1:
            errors.append(
                f"{lbl} has {len(issue_writers)} writers: "
                f"{', '.join(sorted(issue_writers))}"
            )
            continue
        actual = next(iter(issue_writers))
        if actual != expected:
            errors.append(
                f"{lbl}: configured writer `{expected}` does not match "
                f"actual writer `{actual}`"
            )

    # 4. pr-marker: at least one writer, every writer matches the glob.
    # Channel-agnostic because pr-marker labels can be applied via
    # `create-pull-request.labels` (e.g. `agent:autofix`), via
    # `add-labels.allowed` on existing PRs (e.g. `agent:conflict`), or even
    # via `create-issue.labels` for meta-feedback markers raised against the
    # source repo (e.g. `agent:worker-tuning`).
    #
    # `writer` may be a single glob string or a list of glob strings; a
    # writer matches if at least one glob in the list matches it. The list
    # form supports labels stamped by chores that share no name prefix —
    # e.g. `agent:auto-merge` is written by both `trivial-dep-bump-*` (deps
    # PRs) and `worker-fix` (chore-fix PRs).
    for lbl, spec in classes.items():
        if not isinstance(spec, dict) or spec.get("class") != "pr-marker":
            continue
        glob_spec = spec.get("writer")
        if not glob_spec:
            errors.append(f"{lbl}: pr-marker entry missing `writer:` field")
            continue
        if isinstance(glob_spec, str):
            globs = [glob_spec]
        elif isinstance(glob_spec, list) and all(
            isinstance(g, str) for g in glob_spec
        ):
            globs = list(glob_spec)
        else:
            errors.append(
                f"{lbl}: pr-marker `writer:` must be a string or list of "
                f"strings, got {type(glob_spec).__name__}"
            )
            continue
        all_writers = writers.get(lbl, LabelWriters()).any()
        if not all_writers:
            errors.append(
                f"{lbl} has no writer: declared as pr-marker with "
                f"writer=`{glob_spec}` but no workflow writes it"
            )
            continue
        for w in sorted(all_writers):
            if not any(fnmatch.fnmatchcase(w, g) for g in globs):
                errors.append(
                    f"{lbl}: writer `{w}` does not match any configured "
                    f"glob in {globs}"
                )

    # 5. handoff: cross-check writer + consumer sets against config.
    for lbl, spec in classes.items():
        if not isinstance(spec, dict) or spec.get("class") != "handoff":
            continue
        actual_writers = writers.get(lbl, LabelWriters()).any()
        expected_writers = set(config.get("handoff_writers", []) or [])
        if actual_writers != expected_writers:
            missing = expected_writers - actual_writers
            extra = actual_writers - expected_writers
            parts: list[str] = []
            if extra:
                parts.append(
                    f"chores write `{lbl}` but are not in handoff_writers: "
                    f"{', '.join(sorted(extra))}"
                )
            if missing:
                parts.append(
                    f"handoff_writers lists chores that do not write `{lbl}`: "
                    f"{', '.join(sorted(missing))}"
                )
            errors.append(
                (f"{lbl} writer mismatch — " + "; ".join(parts)) if parts
                else f"{lbl} writer mismatch"
            )

        actual_consumers = collect_handoff_consumers(workflow_paths, lbl)
        expected_consumers = set(config.get("handoff_consumers", []) or [])
        if actual_consumers != expected_consumers:
            missing = expected_consumers - actual_consumers
            extra = actual_consumers - expected_consumers
            parts = []
            if extra:
                parts.append(
                    f"workflows reference `{lbl}` but are not in "
                    f"handoff_consumers: {', '.join(sorted(extra))}"
                )
            if missing:
                parts.append(
                    f"handoff_consumers lists workflows that do not "
                    f"reference `{lbl}`: {', '.join(sorted(missing))}"
                )
            errors.append(
                (f"{lbl} consumer mismatch — " + "; ".join(parts)) if parts
                else f"{lbl} consumer mismatch"
            )

    if errors:
        print("label-classification check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    n_labels = len(inventory)
    n_workflows = len(workflow_paths)
    print(
        f"label-classification check OK "
        f"({n_labels} labels across {n_workflows} workflows)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
