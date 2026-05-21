#!/usr/bin/env python3
"""strip-invalid-queue-key.py — remove `queue: max` lines emitted by gh-aw.

gh-aw's codegen emits an extension key `queue: max` under `concurrency:` blocks
in every `.lock.yml` it produces. This key is NOT valid GitHub Actions syntax:
the only accepted children of `concurrency:` are `group:` and
`cancel-in-progress:`. actionlint flags it as `syntax-check` failure and GitHub
Actions silently drops it at runtime — the queueing behavior the codegen
intended is lost.

Until the upstream gh-aw bug is fixed (see ch-oracles issue #28), this script
post-processes lock files after `gh aw compile` and strips the offending lines.
It is intentionally minimal: it only removes lines whose stripped content
exactly equals `queue: max` AND that sit directly inside a `concurrency:`
block. False positives elsewhere would be a problem in user code, not gh-aw
output, so the narrow match is correct.

Usage:
    python scripts/strip-invalid-queue-key.py [--check] .github/workflows/*.lock.yml

Without `--check`, the script rewrites files in place and prints a summary.
With `--check`, the script exits 1 if any lock file still contains the key
(used in CI to ensure the recompile + strip pipeline ran).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Match a line that is exactly `queue: max` (with arbitrary leading whitespace
# and optional trailing whitespace). We do not strip lines like `# queue: max`
# (comments) or `queue: maxsomething` (different value).
QUEUE_MAX_RE = re.compile(r"^[ \t]*queue:[ \t]+max[ \t]*$")


CONCURRENCY_RE = re.compile(r"^([ \t]*)concurrency:[ \t]*$")


def strip_file(path: Path, *, check: bool) -> tuple[int, bool]:
    """Return (lines_removed, modified). In --check mode, never write.

    Only strips `queue: max` lines that sit directly inside a `concurrency:`
    block (indented strictly more than the `concurrency:` line itself). A line
    whose indent falls back to or below the concurrency-line's indent ends
    the block.
    """
    original = path.read_text(encoding="utf-8")
    new_lines: list[str] = []
    removed = 0
    concurrency_indent: int | None = None
    for line in original.splitlines(keepends=True):
        raw = line.rstrip("\n")
        stripped = raw.lstrip(" \t")
        indent = len(raw) - len(stripped)
        if not stripped:
            # Blank line — preserve block context (YAML allows blanks in maps).
            new_lines.append(line)
            continue
        m = CONCURRENCY_RE.match(raw)
        if m:
            concurrency_indent = len(m.group(1))
            new_lines.append(line)
            continue
        if concurrency_indent is not None and indent <= concurrency_indent:
            # Block ended.
            concurrency_indent = None
        if (
            concurrency_indent is not None
            and indent > concurrency_indent
            and QUEUE_MAX_RE.match(raw)
        ):
            removed += 1
            continue
        new_lines.append(line)
    if removed == 0:
        return 0, False
    if check:
        return removed, True
    path.write_text("".join(new_lines), encoding="utf-8")
    return removed, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="lock files to scrub")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any file still contains the invalid key; never writes",
    )
    args = parser.parse_args()

    total_removed = 0
    offending: list[Path] = []
    for path in args.files:
        if not path.is_file():
            sys.stderr.write(f"warn: not a file: {path}\n")
            continue
        removed, modified = strip_file(path, check=args.check)
        if modified:
            total_removed += removed
            offending.append(path)
            verb = "would strip" if args.check else "stripped"
            print(f"{verb} {removed} occurrence(s) of `queue: max` from {path}")

    if args.check and offending:
        sys.stderr.write(
            f"\nerror: {len(offending)} lock file(s) still contain invalid "
            "`queue: max` keys. Run `python scripts/strip-invalid-queue-key.py "
            ".github/workflows/*.lock.yml` after `gh aw compile` and commit "
            "the result.\n"
        )
        return 1

    if not args.check:
        print(f"\ndone: removed {total_removed} line(s) across {len(offending)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
