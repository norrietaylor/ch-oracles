#!/usr/bin/env python3
"""audit-wrapper-permissions.py — CI gate that verifies each wrapper's declared
permissions are no broader than the inner lock file's job-level permissions.

A wrapper that grants more permission than its callee needs is a misconfiguration
that allows the callee to perform operations beyond its declared safe-output
scope. The opposite — wrapper too narrow — produces a startup_failure that
surfaces immediately, so it does not need a CI gate.

Usage:
    python scripts/audit-wrapper-permissions.py wrappers/*.yml
    python scripts/audit-wrapper-permissions.py --workflows-dir .github/workflows --wrappers-dir wrappers
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
    return PERMISSION_LEVELS.get(value.lower(), 0)


def check_pair(wrapper_path: Path, lock_path: Path) -> list[str]:
    """Return a list of violation messages; empty list means OK."""
    violations: list[str] = []
    wrapper = load_yaml(wrapper_path)
    lock = load_yaml(lock_path)

    wrapper_perms = wrapper.get("permissions") or {}
    if not isinstance(wrapper_perms, dict):
        return [f"{wrapper_path}: workflow-level permissions must be a mapping, not {type(wrapper_perms).__name__}"]

    # Collect every job-level permission set in the lock file.
    jobs = lock.get("jobs") or {}
    for job_name, job_def in jobs.items():
        job_perms = (job_def or {}).get("permissions") or {}
        if not isinstance(job_perms, dict):
            continue
        for scope, declared in job_perms.items():
            wrapper_level = normalize_perm(wrapper_perms.get(scope))
            lock_level = normalize_perm(declared)
            if wrapper_level > lock_level:
                violations.append(
                    f"{wrapper_path}: scope '{scope}' grants '{wrapper_perms.get(scope)}' "
                    f"but lock job '{job_name}' declares '{declared}' (over-permission)"
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
    for wrapper_path in wrappers:
        lock_path = Path(args.workflows_dir) / f"{wrapper_path.stem}.lock.yml"
        if not lock_path.exists():
            sys.stderr.write(f"warn: no lock file for {wrapper_path.name} (looked at {lock_path})\n")
            continue
        all_violations.extend(check_pair(wrapper_path, lock_path))

    if all_violations:
        sys.stderr.write("wrapper-permission-cap violations:\n")
        for v in all_violations:
            sys.stderr.write(f"  - {v}\n")
        return 1

    print(f"checked {len(wrappers)} wrappers; zero over-permission violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
