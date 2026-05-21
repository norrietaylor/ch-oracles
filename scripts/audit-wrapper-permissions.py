#!/usr/bin/env python3
"""audit-wrapper-permissions.py — CI gate that verifies each wrapper's declared
workflow-level permissions match the contract demanded by its inner lock file.

A gh-aw lock file contains multiple jobs: activation (read-only), the agent
(typically read-only — writes flow through safe-outputs), detect/detection
jobs (read-only), and emitter jobs that gh-aw injects when safe-outputs is
configured (these need issues:write, pull-requests:write, contents:write to
perform the actual GitHub API calls). The wrapper's workflow-level
permissions cap the union of every job's request, so the audit compares the
wrapper's grant against the max across jobs — not against any single job.

Two failure modes are gated:

1. **over-grant** (wrapper > lock max): the wrapper hands out more
   permission than any job inside the lock actually requests. This is a
   least-privilege regression — the wrapper should be tightened to match
   the lock's true ceiling.
2. **under-grant** (wrapper < lock max): the wrapper grants less
   permission than at least one job in the lock requires. GitHub rejects
   the reusable-workflow invocation with `startup_failure` and no
   annotation, so consumers see a silent breakage. The wrapper must be
   widened to cover the lock's contract. This is the regression class
   that caused issue #13.

Usage:
    python scripts/audit-wrapper-permissions.py wrappers/*.yml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML required. install with: pip install pyyaml\n")
    sys.exit(2)


PERMISSION_LEVELS = {
    "none": 0,
    "read": 1,
    "write": 2,
}


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def normalize_perm(value: str | None) -> int:
    if value is None:
        return 0
    return PERMISSION_LEVELS.get(str(value).lower(), 0)


def max_perm_per_scope(jobs: dict) -> dict[str, str]:
    """For each scope, return the highest permission level any job in the lock requests."""
    out: dict[str, str] = {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        perms = job.get("permissions") or {}
        if not isinstance(perms, dict):
            continue
        for scope, declared in perms.items():
            if normalize_perm(declared) > normalize_perm(out.get(scope)):
                out[scope] = str(declared)
    return out


def check_pair(wrapper_path: Path, lock_path: Path) -> list[str]:
    """Return a list of violation messages; empty list means OK."""
    violations: list[str] = []
    wrapper = load_yaml(wrapper_path)
    lock = load_yaml(lock_path)

    wrapper_perms = wrapper.get("permissions") or {}
    if not isinstance(wrapper_perms, dict):
        return [f"{wrapper_path}: workflow-level permissions must be a mapping, not {type(wrapper_perms).__name__}"]

    jobs = lock.get("jobs") or {}
    if not isinstance(jobs, dict):
        return [f"{lock_path}: jobs must be a mapping"]

    lock_max = max_perm_per_scope(jobs)

    # Over-grant: wrapper hands out more than any lock job requests.
    for scope, wrapper_value in wrapper_perms.items():
        if normalize_perm(wrapper_value) > normalize_perm(lock_max.get(scope)):
            violations.append(
                f"{wrapper_path}: scope '{scope}' grants '{wrapper_value}' "
                f"but no lock job exceeds '{lock_max.get(scope, 'none')}' (over-permission)"
            )

    # Under-grant: wrapper grants less than at least one lock job needs.
    # Without this, GitHub returns `startup_failure` with no annotation when
    # the wrapper is invoked — a silent breakage (issue #13).
    for scope, lock_value in lock_max.items():
        wrapper_value = wrapper_perms.get(scope)
        if normalize_perm(wrapper_value) < normalize_perm(lock_value):
            violations.append(
                f"{wrapper_path}: scope '{scope}' grants '{wrapper_value or 'none'}' "
                f"but lock requires '{lock_value}' (under-permission — will cause startup_failure)"
            )
    return violations


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("wrappers", nargs="*", help="wrapper YAML files to check")
    p.add_argument("--wrappers-dir", default="wrappers")
    p.add_argument("--workflows-dir", default=".github/workflows")
    args = p.parse_args()

    if args.wrappers:
        wrappers = [Path(w) for w in args.wrappers]
    else:
        wrappers = sorted(Path(args.wrappers_dir).glob("*.yml"))

    if not wrappers:
        sys.stderr.write(f"no wrappers found in {args.wrappers_dir}\n")
        return 2

    all_violations: list[str] = []
    checked = 0
    for wrapper_path in wrappers:
        lock_path = Path(args.workflows_dir) / f"{wrapper_path.stem}.lock.yml"
        if not lock_path.exists():
            sys.stderr.write(f"warn: no lock file for {wrapper_path.name} (looked at {lock_path})\n")
            continue
        all_violations.extend(check_pair(wrapper_path, lock_path))
        checked += 1

    if all_violations:
        sys.stderr.write("wrapper-permission-cap violations:\n")
        for v in all_violations:
            sys.stderr.write(f"  - {v}\n")
        return 1

    print(f"checked {checked} wrappers; zero permission violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
