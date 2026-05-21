#!/usr/bin/env python3
"""test-wrapper-permissions.py — unit tests for the wrapper-permission audit.

Verifies `scripts/audit-wrapper-permissions.py` correctly identifies both
classes of violations:

1. **Over-grant**: wrapper hands out more permission than any job inside
   the lock requests (least-privilege regression).
2. **Under-grant**: wrapper grants less permission than at least one job
   in the lock requires. GitHub returns `startup_failure` with no
   annotation when the reusable-workflow contract is under-satisfied
   (the regression class behind issue #13).

The audit script is invoked as a subprocess against synthetic wrapper +
lock YAML fixtures in a tmpdir, so the test exercises the real CLI exit
code and stderr message contract.

Usage:
    python scripts/test-wrapper-permissions.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "audit-wrapper-permissions.py"


def write_wrapper(path: Path, perms: dict[str, str]) -> None:
    perm_lines = "\n".join(f"  {k}: {v}" for k, v in perms.items())
    path.write_text(
        f"""name: example
on:
  workflow_dispatch:

permissions:
{perm_lines}

jobs:
  run:
    uses: gominimal/ch-oracles/.github/workflows/example.lock.yml@main
"""
    )


def write_lock(path: Path, jobs: dict[str, dict[str, str]]) -> None:
    """Each job is a dict of scope→level. Always passes through a minimal
    runs-on so the YAML parses as a credible workflow."""
    job_blocks = []
    for jname, perms in jobs.items():
        perm_yaml = (
            "\n".join(f"      {k}: {v}" for k, v in perms.items()) if perms else "{}"
        )
        if perms:
            job_blocks.append(
                f"  {jname}:\n    runs-on: ubuntu-latest\n    permissions:\n{perm_yaml}\n    steps:\n      - run: 'true'"
            )
        else:
            job_blocks.append(
                f"  {jname}:\n    runs-on: ubuntu-latest\n    permissions: {{}}\n    steps:\n      - run: 'true'"
            )
    body = "\n".join(job_blocks)
    path.write_text(
        f"""name: example
on:
  workflow_call: {{}}

jobs:
{body}
"""
    )


def run_audit(workdir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(workdir / "wrappers" / "example.yml"),
            "--workflows-dir",
            str(workdir / ".github/workflows"),
        ],
        capture_output=True,
        text=True,
    )


def setup_case(tmp: Path, wrapper_perms: dict, lock_jobs: dict) -> Path:
    (tmp / "wrappers").mkdir(parents=True, exist_ok=True)
    (tmp / ".github/workflows").mkdir(parents=True, exist_ok=True)
    write_wrapper(tmp / "wrappers/example.yml", wrapper_perms)
    write_lock(tmp / ".github/workflows/example.lock.yml", lock_jobs)
    return tmp


# --- test cases ----------------------------------------------------------


def test_matched_permissions_pass() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = setup_case(
            Path(td),
            wrapper_perms={
                "actions": "read",
                "contents": "write",
                "issues": "write",
                "pull-requests": "write",
            },
            lock_jobs={
                "activation": {"actions": "read", "contents": "read"},
                "agent": {"contents": "read"},
                "safe_outputs": {
                    "contents": "write",
                    "issues": "write",
                    "pull-requests": "write",
                },
            },
        )
        result = run_audit(tmp)
        assert result.returncode == 0, (
            f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "zero permission violations" in result.stdout


def test_over_grant_detected() -> None:
    """Wrapper grants `contents: write` but no lock job exceeds `read`."""
    with tempfile.TemporaryDirectory() as td:
        tmp = setup_case(
            Path(td),
            wrapper_perms={"actions": "read", "contents": "write"},
            lock_jobs={
                "activation": {"actions": "read", "contents": "read"},
                "agent": {"contents": "read"},
            },
        )
        result = run_audit(tmp)
        assert result.returncode == 1, (
            f"expected exit 1, got {result.returncode}\nstderr: {result.stderr}"
        )
        assert "over-permission" in result.stderr
        assert "contents" in result.stderr


def test_under_grant_detected() -> None:
    """Wrapper grants `contents: read` but a lock job requires `contents: write`.

    This is the issue #13 regression: GitHub returns startup_failure with no
    annotation when the reusable-workflow contract is under-satisfied.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = setup_case(
            Path(td),
            wrapper_perms={
                "actions": "read",
                "contents": "read",
                "issues": "write",
                "pull-requests": "write",
            },
            lock_jobs={
                "activation": {"actions": "read", "contents": "read"},
                "safe_outputs": {
                    "contents": "write",
                    "issues": "write",
                    "pull-requests": "write",
                },
            },
        )
        result = run_audit(tmp)
        assert result.returncode == 1, (
            f"expected exit 1, got {result.returncode}\nstderr: {result.stderr}"
        )
        assert "under-permission" in result.stderr
        assert "startup_failure" in result.stderr
        assert "contents" in result.stderr


def test_missing_scope_in_wrapper_is_under_grant() -> None:
    """A scope that the lock requires but the wrapper omits entirely is an
    under-grant — omitted scopes default to `none` in the workflow_call
    contract."""
    with tempfile.TemporaryDirectory() as td:
        tmp = setup_case(
            Path(td),
            # wrapper has no `issues` entry at all
            wrapper_perms={"contents": "write"},
            lock_jobs={
                "safe_outputs": {"contents": "write", "issues": "write"},
            },
        )
        result = run_audit(tmp)
        assert result.returncode == 1, (
            f"expected exit 1, got {result.returncode}\nstderr: {result.stderr}"
        )
        assert "under-permission" in result.stderr
        assert "issues" in result.stderr


def test_under_and_over_grant_both_reported() -> None:
    """When a wrapper is wrong in both directions on different scopes, the
    audit must surface both violations, not short-circuit."""
    with tempfile.TemporaryDirectory() as td:
        tmp = setup_case(
            Path(td),
            wrapper_perms={
                # under-grant on contents (lock needs write, wrapper grants read)
                "contents": "read",
                # over-grant on actions (lock needs read at most, wrapper grants write)
                "actions": "write",
            },
            lock_jobs={
                "activation": {"actions": "read", "contents": "read"},
                "safe_outputs": {"contents": "write"},
            },
        )
        result = run_audit(tmp)
        assert result.returncode == 1
        assert "under-permission" in result.stderr
        assert "over-permission" in result.stderr


def test_real_repo_wrappers_pass() -> None:
    """End-to-end: the audit must pass against the wrappers and locks
    checked into this repo. If this fails, either a wrapper has drifted from
    its lock's contract, or the audit logic has regressed."""
    repo_root = Path(__file__).resolve().parent.parent
    wrappers = sorted((repo_root / "wrappers").glob("*.yml"))
    if not wrappers:
        # Repo layout changed; skip rather than false-fail.
        return
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(w) for w in wrappers]],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        f"audit failed against real repo wrappers (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# --- runner --------------------------------------------------------------


def main() -> int:
    tests = [
        test_matched_permissions_pass,
        test_over_grant_detected,
        test_under_grant_detected,
        test_missing_scope_in_wrapper_is_under_grant,
        test_under_and_over_grant_both_reported,
        test_real_repo_wrappers_pass,
    ]
    failures: list[str] = []
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures.append(f"{t.__name__}: {e}")
            print(f"FAIL  {t.__name__}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{t.__name__}: {type(e).__name__}: {e}")
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} of {len(tests)} tests failed.", file=sys.stderr)
        return 1
    print(f"\nall {len(tests)} tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
