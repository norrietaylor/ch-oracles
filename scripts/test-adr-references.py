#!/usr/bin/env python3
"""test-adr-references.py — CI gate that verifies every ADR citation in the
source tree resolves to a real ADR file, and (as a warning) surfaces ADRs
that no longer participate in the live design.

What it checks:

1. **Unresolved prose citations.** Every `ADR <NNNN>` mention in scoped
   sources (workflows, shared, wrappers, templates/.github, docs, README,
   mkdocs.yml, ADRs themselves) must resolve to a `decisions/<NNNN>-*.md`
   file. Fails the gate.

2. **Stale path citations.** Every `decisions/<NNNN>-<slug>.md` path mention
   must match an existing ADR filename exactly. Catches renames where a
   citation was not updated. Fails the gate.

3. **Dead ADRs (warning only).** Any ADR file not cited live outside
   `decisions/` is reported to stderr as a warning. Does not fail the gate;
   surfaces ADRs that have lost their connection to the live design so a
   human can decide whether to re-cite, supersede, or retire.

4. **Supersession pointers.** If an ADR's `Status:` line names a
   `Superseded by: ADR <NNNN>` pointer, the target must exist. Fails the
   gate when the pointer dangles.

Cross-repo ADR references (per ADR 0003's coexistence note) are out of
scope: a citation inside a `[text](url)` markdown link whose URL points to
a non-`ch-oracles` GitHub repo is ignored.

Usage:
    python scripts/test-adr-references.py [--repo-root <path>]

Exit codes:
    0 — no errors (warnings may still print)
    1 — one or more unresolved/stale references
    2 — script misuse (no ADRs found, scope error)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Filename of a canonical ADR: 0NNN-<slug>.md (slug is lowercase + hyphens
# + digits per existing convention).
ADR_FILENAME_RE = re.compile(r"^(0\d{3})-([a-z0-9-]+)\.md$")

# Prose citation form: "ADR 0001", "ADR-0004", "ADR 1234". Captures the ID
# (we'll zero-pad to 4 digits). The character class `[\s-]*` permits an
# optional hyphen or whitespace between "ADR" and the digits.
ADR_PROSE_RE = re.compile(r"\bADR[\s-]*0?(\d{3,4})\b")

# Path citation form: "decisions/0006-engine-split.md". Captures the full
# filename so we can require an exact match against the on-disk file.
ADR_PATH_RE = re.compile(r"decisions/(0\d{3}-[a-z0-9-]+\.md)")

# Markdown link with explicit URL: [text](url). We use this to identify
# cross-repo citations that should be ignored.
MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")

# The github.com host pattern for repo extraction.
GH_URL_RE = re.compile(r"https?://github\.com/([^/\s]+)/([^/\s)]+)")

# Supersession pointer in an ADR status line.
SUPERSEDED_BY_RE = re.compile(r"Superseded by:\s*ADR[\s-]*0?(\d{3,4})", re.IGNORECASE)

LOCAL_REPO_SLUG = "ch-oracles"


def normalize_id(raw: str) -> str:
    """Zero-pad a captured ADR id to 4 digits ('1' -> '0001', '42' -> '0042')."""
    return raw.zfill(4)


def is_cross_repo_link(url: str) -> bool:
    """A markdown link whose URL points to a github.com repo other than
    ch-oracles is cross-repo. URLs that are not github.com (relative,
    fragment, mailto) are NOT cross-repo: a fragment or relative link
    still points at this tree.
    """
    m = GH_URL_RE.match(url)
    if not m:
        return False
    _owner, repo = m.group(1), m.group(2)
    # Repo could have a `.git` suffix or trailing punctuation; strip
    # anything after the first non-name char.
    repo = re.split(r"[^a-zA-Z0-9_.-]", repo, maxsplit=1)[0]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return repo != LOCAL_REPO_SLUG


def strip_cross_repo_links(line: str) -> str:
    """Replace cross-repo markdown links with whitespace placeholders so
    they neither match ADR prose nor path regexes.

    Whitespace (not empty) preserves column offsets if a caller wants to
    report them; functionally either is fine.
    """
    def repl(m: re.Match[str]) -> str:
        """re.sub callback: blank out the link if it points to another repo."""
        url = m.group(2)
        if is_cross_repo_link(url):
            return " " * (m.end() - m.start())
        return m.group(0)
    return MD_LINK_RE.sub(repl, line)


def discover_adrs(decisions_dir: Path) -> dict[str, str]:
    """Return {adr_id: filename} for every ADR matching the canonical form.

    Files in decisions/ that do not match the canonical pattern (e.g.
    README.md, an index, a draft outside the numbered scheme) are ignored
    silently; this script does not police what lives alongside ADRs.
    """
    adrs: dict[str, str] = {}
    if not decisions_dir.is_dir():
        return adrs
    for path in sorted(decisions_dir.iterdir()):
        if not path.is_file():
            continue
        m = ADR_FILENAME_RE.match(path.name)
        if not m:
            continue
        adr_id = m.group(1)
        if adr_id in adrs:
            # Duplicate id under different slugs would be a structural
            # problem; flag it loud.
            sys.stderr.write(
                f"error: duplicate ADR id {adr_id} — {adrs[adr_id]} and {path.name}\n"
            )
            sys.exit(2)
        adrs[adr_id] = path.name
    return adrs


def collect_sources(repo_root: Path) -> list[Path]:
    """Return the ordered list of source files to scan for ADR citations.

    Scope matches the issue: workflows, shared, wrappers, templates'
    .github/, docs/**/*.md, README.md, mkdocs.yml, and the ADRs themselves
    (so supersession + cross-ADR citations are validated).
    """
    sources: list[Path] = []

    def add_glob(pattern: str, recursive: bool = False) -> None:
        """Append every file matching pattern (relative to repo_root) to sources."""
        it = (repo_root.glob(pattern) if not recursive
              else repo_root.rglob(pattern))
        for p in sorted(it):
            if p.is_file():
                sources.append(p)

    add_glob("workflows/*.md")
    add_glob("shared/*.md")
    add_glob("wrappers/*.yml")
    add_glob("templates/.github/*.md")
    # docs/**/*.md — recursive so docs/languages/*.md is included.
    for p in sorted((repo_root / "docs").rglob("*.md")):
        if p.is_file():
            sources.append(p)

    for name in ("README.md", "mkdocs.yml"):
        p = repo_root / name
        if p.is_file():
            sources.append(p)

    # ADRs themselves — for supersession + cross-ADR references.
    for p in sorted((repo_root / "decisions").glob("*.md")):
        if p.is_file():
            sources.append(p)

    return sources


def resolve_prose_citations(
    sources: list[Path], adrs: dict[str, str], repo_root: Path
) -> tuple[dict[str, set[Path]], list[str]]:
    """Walk sources, return ({adr_id: {citing_paths}}, error_lines)."""
    citers: dict[str, set[Path]] = {}
    errors: list[str] = []
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(repo_root)
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = strip_cross_repo_links(raw_line)

            for m in ADR_PROSE_RE.finditer(line):
                adr_id = normalize_id(m.group(1))
                if adr_id not in adrs:
                    errors.append(
                        f"{rel}:{line_no}: unresolved ADR reference: ADR "
                        f"{adr_id} ({m.group(0)!r}) — no decisions/{adr_id}-*.md"
                    )
                else:
                    citers.setdefault(adr_id, set()).add(path)

            for m in ADR_PATH_RE.finditer(line):
                full = m.group(1)
                file_m = ADR_FILENAME_RE.match(full)
                if not file_m:
                    errors.append(
                        f"{rel}:{line_no}: malformed ADR path — {full!r}"
                    )
                    continue
                adr_id = file_m.group(1)
                if adr_id not in adrs:
                    errors.append(
                        f"{rel}:{line_no}: unresolved ADR path: "
                        f"decisions/{full} — no such ADR file"
                    )
                elif adrs[adr_id] != full:
                    # ID exists but the slug differs → stale rename.
                    errors.append(
                        f"{rel}:{line_no}: stale ADR path: decisions/{full} "
                        f"— ADR {adr_id} now lives at decisions/{adrs[adr_id]}"
                    )
                else:
                    citers.setdefault(adr_id, set()).add(path)
    return citers, errors


def check_supersessions(
    adrs: dict[str, str], repo_root: Path
) -> tuple[dict[str, str], list[str]]:
    """Parse each ADR's status line. Return ({adr_id: superseded_by_id},
    error_lines for dangling pointers).
    """
    superseded_by: dict[str, str] = {}
    errors: list[str] = []
    decisions_dir = repo_root / "decisions"
    for adr_id, filename in sorted(adrs.items()):
        path = decisions_dir / filename
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.lstrip().startswith("Status:"):
                continue
            m = SUPERSEDED_BY_RE.search(line)
            if not m:
                continue
            target = normalize_id(m.group(1))
            if target not in adrs:
                errors.append(
                    f"decisions/{filename}:{line_no}: superseded-by pointer "
                    f"to ADR {target} — no such ADR file"
                )
                continue
            superseded_by[adr_id] = target
    return superseded_by, errors


def find_dead_adrs(
    adrs: dict[str, str],
    citers: dict[str, set[Path]],
    superseded_by: dict[str, str],
    repo_root: Path,
) -> list[str]:
    """Return warning lines for ADRs that lack a live citation outside
    decisions/.

    A 'live' citation is one from any source that is NOT itself in
    decisions/. Self-mentions don't count. ADRs marked as Superseded are
    exempt from the live-citation requirement, but their superseder MUST
    be cited live (enforced as a hard error elsewhere if we ever ship
    supersession).
    """
    warnings: list[str] = []
    decisions_dir = repo_root / "decisions"
    for adr_id, filename in sorted(adrs.items()):
        live = {
            p for p in citers.get(adr_id, set())
            if decisions_dir not in p.parents
        }
        if live:
            continue
        if adr_id in superseded_by:
            # Superseded ADRs are allowed to fall out of live citation.
            continue
        warnings.append(
            f"warning: decisions/{filename}: dead ADR — no live citation "
            "outside decisions/ (workflow/shared/wrapper/template/docs/README/mkdocs)"
        )
    return warnings


def main() -> int:
    """CLI entry point. Discover ADRs, scan sources, validate, and exit."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--repo-root",
        default=".",
        help="repository root (default: current working directory)",
    )
    p.add_argument(
        "--strict-dead",
        action="store_true",
        help="treat dead-ADR warnings as errors (exit 1).",
    )
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    decisions_dir = repo_root / "decisions"

    adrs = discover_adrs(decisions_dir)
    if not adrs:
        sys.stderr.write(
            f"error: no ADRs found under {decisions_dir} (expected "
            "0NNN-<slug>.md files)\n"
        )
        return 2

    sources = collect_sources(repo_root)
    if not sources:
        sys.stderr.write("error: no source files in scope to scan\n")
        return 2

    citers, ref_errors = resolve_prose_citations(sources, adrs, repo_root)
    superseded_by, supersession_errors = check_supersessions(adrs, repo_root)
    dead_warnings = find_dead_adrs(adrs, citers, superseded_by, repo_root)

    # Print results.
    all_errors = ref_errors + supersession_errors
    for line in all_errors:
        sys.stderr.write(line + "\n")
    for line in dead_warnings:
        sys.stderr.write(line + "\n")

    if all_errors:
        sys.stderr.write(
            f"\nadr-refs: {len(all_errors)} error(s) across "
            f"{len(adrs)} ADR(s) and {len(sources)} source file(s).\n"
        )
        return 1
    if args.strict_dead and dead_warnings:
        sys.stderr.write(
            f"\nadr-refs: {len(dead_warnings)} dead ADR(s) under --strict-dead.\n"
        )
        return 1

    print(
        f"adr-refs: {len(adrs)} ADR(s), {len(sources)} source file(s) "
        f"scanned, {sum(len(c) for c in citers.values())} citation(s) "
        f"resolved, {len(dead_warnings)} dead-ADR warning(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
