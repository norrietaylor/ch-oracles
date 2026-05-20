#!/usr/bin/env bash
# scripts/quick-setup.sh — install ch-oracles into a consumer repository.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/norrietaylor/ch-oracles/main/scripts/quick-setup.sh \
#     | bash -s -- --suite oracles
#
# Flags:
#   --suite oracles              Install all ch-oracles wrappers (default).
#   --languages rust,python,...  Filter wrappers to declared languages.
#                                Default: auto-detect via manifest sniff.
#   --with-workers               Include worker-fix, worker-iterate, pr-conflict-resolver.
#   --no-templates               Skip AGENTS.md + labels.yml + issue-template insertion.
#   --source-ref <ref>           Pin the ch-oracles release tag/sha in wrappers (default: main).
#   --update                     Refresh existing install; preserve user-edited sections.
#   --target <dir>               Install into <dir> instead of the current working directory.
#                                Implies the target need not be a git repo.
#   --dry-run                    Smoke mode: source files from the local ch-oracles checkout
#                                (the directory containing this script) instead of curl, skip
#                                the post-install operator message. Side effects on the target
#                                directory still occur so install assertions can run; the source
#                                repo is never touched. Intended for CI smoke tests.

set -euo pipefail

SOURCE_REPO="norrietaylor/ch-oracles"
SOURCE_RAW="https://raw.githubusercontent.com/${SOURCE_REPO}"
SOURCE_REF="main"
SUITE="oracles"
LANGUAGES=""
WITH_WORKERS=0
NO_TEMPLATES=0
UPDATE=0
DRY_RUN=0
REPO_ROOT="$(pwd)"
TARGET_OVERRIDE=""

# Resolve the local ch-oracles checkout root (parent of scripts/). Used in
# dry-run mode as the source-of-truth for wrapper and template files.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  sed -n '2,22p' "$0"
  exit 0
}

log()    { printf '[ch-oracles] %s\n' "$*"; }
warn()   { printf '[ch-oracles] WARN: %s\n' "$*" >&2; }
die()    { printf '[ch-oracles] ERROR: %s\n' "$*" >&2; exit 1; }
# Removed do_or_dry helper (SC2294 eval misuse). Each call site below handles
# its own dry-run check inline so the dispatched command can use a real argv
# array rather than `eval` re-splitting a string.

while [ $# -gt 0 ]; do
  case "$1" in
    --suite) SUITE="$2"; shift 2 ;;
    --languages) LANGUAGES="$2"; shift 2 ;;
    --with-workers) WITH_WORKERS=1; shift ;;
    --no-templates) NO_TEMPLATES=1; shift ;;
    --source-ref) SOURCE_REF="$2"; shift 2 ;;
    --update) UPDATE=1; shift ;;
    --target) TARGET_OVERRIDE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown flag: $1 (use --help)" ;;
  esac
done

[ "${SUITE}" = "oracles" ] || die "unsupported suite: ${SUITE} (only 'oracles' is supported)"

if [ -n "${TARGET_OVERRIDE}" ]; then
  mkdir -p "${TARGET_OVERRIDE}"
  REPO_ROOT="$(cd "${TARGET_OVERRIDE}" && pwd)"
fi

if [ "${DRY_RUN}" -eq 1 ]; then
  # In dry-run we don't require the target to be a git repo (fixture dirs aren't).
  # Default the language list when detection finds nothing, so the smoke is hermetic.
  :
else
  [ -d "${REPO_ROOT}/.git" ] || die "not a git repository: ${REPO_ROOT}"
fi

if [ -d "${REPO_ROOT}/.git" ]; then
  REPO_NAME="$(basename "$(git -C "${REPO_ROOT}" rev-parse --show-toplevel)")"
else
  REPO_NAME="$(basename "${REPO_ROOT}")"
fi
log "target repo: ${REPO_NAME} (${REPO_ROOT})"
log "source ref:  ${SOURCE_REF}"
log "mode:        $([ "${UPDATE}" -eq 1 ] && echo update || echo install)$([ "${DRY_RUN}" -eq 1 ] && echo ' (dry-run)' || true)"

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

detect_languages() {
  local detected=()
  [ -f "${REPO_ROOT}/Cargo.toml" ] && detected+=("rust")
  [ -f "${REPO_ROOT}/pyproject.toml" ] && detected+=("python")
  [ -f "${REPO_ROOT}/go.mod" ] && detected+=("go")
  # toml: any *.toml outside of Cargo.toml signals taplo's scope
  if find "${REPO_ROOT}" -maxdepth 3 -name '*.toml' -not -path '*/target/*' -not -path '*/node_modules/*' 2>/dev/null | grep -qv 'Cargo\.toml$'; then
    detected+=("toml")
  fi
  # ncl: any *.ncl file under repo
  if find "${REPO_ROOT}" -maxdepth 4 -name '*.ncl' -not -path '*/target/*' -not -path '*/node_modules/*' 2>/dev/null | head -1 | grep -q .; then
    detected+=("ncl")
  fi
  printf '%s\n' "${detected[@]}" | sort -u | paste -sd, -
}

if [ -z "${LANGUAGES}" ]; then
  LANGUAGES="$(detect_languages)"
  [ -z "${LANGUAGES}" ] && die "no supported languages detected; pass --languages explicitly"
  log "detected languages: ${LANGUAGES}"
else
  log "languages (explicit): ${LANGUAGES}"
fi

# ---------------------------------------------------------------------------
# Wrapper installation
# ---------------------------------------------------------------------------

WRAPPERS_DIR=".github/workflows"

# Always-install wrappers (universal chores).
UNIVERSAL_WRAPPERS=(
  docs-patrol
  dependency-review
  test-coverage-detector
)

# Worker wrappers (gated by --with-workers).
WORKER_WRAPPERS=(
  worker-fix
  worker-iterate
  pr-conflict-resolver
)

# Per-language wrappers.
language_wrappers() {
  local lang="$1"
  case "${lang}" in
    rust)   printf 'chore-style-rust\ntrivial-dep-bump-rust\n' ;;
    python) printf 'chore-style-python\ntrivial-dep-bump-python\n' ;;
    go)     printf 'chore-style-go\ntrivial-dep-bump-go\n' ;;
    toml)   printf 'chore-style-toml\n' ;;
    ncl)    printf 'chore-style-ncl\n' ;;
  esac
}

install_wrapper() {
  local name="$1"
  local src_url="${SOURCE_RAW}/${SOURCE_REF}/wrappers/${name}.yml"
  local local_src="${LOCAL_SOURCE_ROOT}/wrappers/${name}.yml"
  local dst="${REPO_ROOT}/${WRAPPERS_DIR}/${name}.yml"

  if [ -f "${dst}" ] && [ "${UPDATE}" -eq 0 ]; then
    warn "skip ${name}.yml (already exists; use --update to overwrite)"
    return
  fi

  log "install ${WRAPPERS_DIR}/${name}.yml"
  mkdir -p "$(dirname "${dst}")"
  if [ "${DRY_RUN}" -eq 1 ]; then
    [ -f "${local_src}" ] || die "dry-run: local wrapper missing: ${local_src}"
    sed "s|{{SOURCE_REF}}|${SOURCE_REF}|g" < "${local_src}" > "${dst}"
    return
  fi
  curl -fsSL "${src_url}" \
    | sed "s|{{SOURCE_REF}}|${SOURCE_REF}|g" \
    > "${dst}"
}

# Compose the wrapper list.
TO_INSTALL=()
TO_INSTALL+=("${UNIVERSAL_WRAPPERS[@]}")

IFS=',' read -ra LANG_LIST <<< "${LANGUAGES}"
for lang in "${LANG_LIST[@]}"; do
  while read -r w; do
    [ -n "${w}" ] && TO_INSTALL+=("${w}")
  done < <(language_wrappers "${lang}")
done

if [ "${WITH_WORKERS}" -eq 1 ]; then
  TO_INSTALL+=("${WORKER_WRAPPERS[@]}")
fi

log "wrappers to install: ${TO_INSTALL[*]}"

for w in "${TO_INSTALL[@]}"; do
  install_wrapper "${w}"
done

# ---------------------------------------------------------------------------
# Template installation
# ---------------------------------------------------------------------------

install_template() {
  local rel_path="$1"
  local src_url="${SOURCE_RAW}/${SOURCE_REF}/templates/${rel_path}"
  local local_src="${LOCAL_SOURCE_ROOT}/templates/${rel_path}"
  local dst="${REPO_ROOT}/${rel_path}"

  if [ -f "${dst}" ] && [ "${UPDATE}" -eq 0 ]; then
    warn "skip ${rel_path} (already exists)"
    return
  fi

  log "install ${rel_path}"
  mkdir -p "$(dirname "${dst}")"
  # Pick the primary language for {{LANGUAGE}} substitution (first detected).
  local primary_lang
  primary_lang="$(printf '%s' "${LANGUAGES}" | cut -d, -f1)"
  if [ "${DRY_RUN}" -eq 1 ]; then
    [ -f "${local_src}" ] || die "dry-run: local template missing: ${local_src}"
    sed "s|{{REPO_NAME}}|${REPO_NAME}|g; s|{{LANGUAGE}}|${primary_lang}|g; s|{{SOURCE_REF}}|${SOURCE_REF}|g" \
      < "${local_src}" > "${dst}"
    return
  fi
  curl -fsSL "${src_url}" \
    | sed "s|{{REPO_NAME}}|${REPO_NAME}|g; s|{{LANGUAGE}}|${primary_lang}|g; s|{{SOURCE_REF}}|${SOURCE_REF}|g" \
    > "${dst}"
}

if [ "${NO_TEMPLATES}" -eq 0 ]; then
  install_template ".github/AGENTS.md"
  install_template ".github/copilot-instructions.md"
  install_template ".github/ISSUE_TEMPLATE/bug.md"
  install_template ".github/ISSUE_TEMPLATE/feature.md"
  install_template ".github/ISSUE_TEMPLATE/chore.md"

  # labels.yml: merge rather than overwrite.
  LABELS_DST="${REPO_ROOT}/.github/labels.yml"
  LABELS_SRC_URL="${SOURCE_RAW}/${SOURCE_REF}/templates/.github/labels.yml"
  LABELS_LOCAL_SRC="${LOCAL_SOURCE_ROOT}/templates/.github/labels.yml"
  if [ -f "${LABELS_DST}" ]; then
    log "labels.yml exists; appending ch-oracles labels (manual merge may be needed)"
    if [ "${DRY_RUN}" -eq 1 ]; then
      [ -f "${LABELS_LOCAL_SRC}" ] || die "dry-run: local labels.yml missing: ${LABELS_LOCAL_SRC}"
      {
        printf '\n# --- ch-oracles labels (merged %s) ---\n' "$(date -u +%Y-%m-%d)"
        cat "${LABELS_LOCAL_SRC}"
      } >> "${LABELS_DST}"
    else
      {
        printf '\n# --- ch-oracles labels (merged %s) ---\n' "$(date -u +%Y-%m-%d)"
        curl -fsSL "${LABELS_SRC_URL}"
      } >> "${LABELS_DST}"
    fi
  else
    install_template ".github/labels.yml"
  fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

log "install complete."
if [ "${DRY_RUN}" -eq 0 ]; then
  log "next steps:"
  log "  1. Review the new files under .github/ and commit them."
  log "  2. Configure repository secrets: APP_PRIVATE_KEY, COPILOT_GITHUB_TOKEN."
  log "  3. Configure repository variables: APP_ID, CH_ORACLES_LANGUAGE (optional)."
  log "  4. Sync labels: gh label sync -f .github/labels.yml"
fi
