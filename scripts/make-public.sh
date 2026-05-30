#!/usr/bin/env bash
# Promote a SwimBlocks repo from private to public.
#
# This script is the **canonical place** where SwimBlocks accumulates pre-public
# checks and post-flip steps. Whenever we learn that something is risky to
# ship publicly, or that something needs to be configured the moment a repo
# becomes public, that check or step belongs here. The intent: nobody should
# have to remember "did I check X?" — running this script is enough.
#
# Usage:
#   scripts/make-public.sh swimblocks/<repo-name> [--yes] [--skip-history]
#
# Flags:
#   --yes           Don't prompt for the confirmation typeback.
#   --skip-history  Skip the git-history secret scan (faster, less safe).
#
# Today the script does:
#   1. Verify the repo is currently private.
#   2. Clone the repo (shallow + full history) into a tmpdir.
#   3. Scan the working tree for secret-shaped strings.
#   4. Scan the git history for the same (unless --skip-history).
#   5. Check for LICENSE and README.md (warn, do not block).
#   6. Confirm with the operator.
#   7. Flip visibility to public.
#   8. Wait for GitHub to release the visibility-flip lock.
#   9. Apply settings.yml (which now installs branch protection too).
#
# Add new checks above. Keep them ordered cheapest-first.
set -euo pipefail

repo="${1:-}"; shift || true
if [ -z "$repo" ]; then
  echo "usage: $0 swimblocks/<repo-name> [--yes] [--skip-history]" >&2
  exit 2
fi

yes=0
skip_history=0
for arg in "$@"; do
  case "$arg" in
    --yes) yes=1 ;;
    --skip-history) skip_history=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# --- 1. current visibility -----------------------------------------------
visibility=$(gh repo view "$repo" --json visibility -q '.visibility')
if [ "$visibility" = "PUBLIC" ]; then
  echo "==> $repo is already PUBLIC. Nothing to do."
  exit 0
fi
echo "==> $repo is $visibility — running pre-public checks"

# --- 2. shallow clone ----------------------------------------------------
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "  - cloning into $tmp ..."
if [ "$skip_history" -eq 1 ]; then
  gh repo clone "$repo" "$tmp/repo" -- --depth=1 --quiet >/dev/null
else
  gh repo clone "$repo" "$tmp/repo" -- --quiet >/dev/null
fi

# --- 3. secret patterns --------------------------------------------------
# Cheap, fast, narrowly-shaped regexes. False positives are OK; false
# negatives aren't. Tracking deeper coverage (gitleaks / trufflehog) under
# https://github.com/swimblocks/.github/issues/8.
SECRET_RE='(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]+PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|GOCSPX-[A-Za-z0-9_-]{28}|xox[abprs]-[0-9]{10,}-[0-9]{10,}|(api[_-]?key|api[_-]?secret|access[_-]?token|client[_-]?secret)[[:space:]]*[:=][[:space:]]*['"'"'"][A-Za-z0-9_-]{20,}['"'"'"]|(mysql|postgres|mongodb)://[^:]+:[^@]+@)'

echo "  - scanning working tree for secret-shaped strings ..."
if git -C "$tmp/repo" grep -nIE "$SECRET_RE" -- ':!*.lock' ':!*lock.json' 2>/dev/null; then
  echo
  echo "FAIL: working tree contains secret-shaped strings (above). Resolve before going public." >&2
  exit 1
fi

# --- 4. git history secret scan -----------------------------------------
if [ "$skip_history" -eq 0 ]; then
  echo "  - scanning git history for secret-shaped strings (use --skip-history to bypass) ..."
  # `git log --all -p` includes deleted content. Stop at first match.
  if git -C "$tmp/repo" log --all -p 2>/dev/null | grep -m1 -nE "$SECRET_RE" >/dev/null; then
    echo
    echo "FAIL: git history contains secret-shaped strings." >&2
    echo "  Scrub with git-filter-repo (or BFG) before making the repo public," >&2
    echo "  or rotate the offending credential and accept the historical exposure." >&2
    exit 1
  fi
fi

# --- 5. required-file audit (warn only) ---------------------------------
echo "  - checking recommended public-repo files ..."
for f in LICENSE README.md; do
  if [ ! -e "$tmp/repo/$f" ]; then
    echo "  WARN: $f not found at repo root. Strongly recommended before going public."
  fi
done

# --- 6. confirm ----------------------------------------------------------
echo
echo "All automated checks complete. About to flip $repo to PUBLIC."
echo "GitHub strongly discourages flipping back, so treat this as irreversible."
if [ "$yes" -eq 0 ]; then
  read -rp "Type the repo name ($(basename "$repo")) to confirm: " confirm
  if [ "$confirm" != "$(basename "$repo")" ]; then
    echo "aborting."; exit 1
  fi
fi

# --- 7. flip -------------------------------------------------------------
echo "==> Flipping visibility to public"
gh repo edit "$repo" --visibility public --accept-visibility-change-consequences

# --- 8. wait for the visibility-flip lock to release ---------------------
echo "==> Waiting for GitHub to release the temporary lock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY="python $SCRIPT_DIR/apply-settings.py"
for i in $(seq 1 15); do
  if $APPLY "$repo" >/dev/null 2>&1; then
    echo "  (lock released after ${i} attempt(s))"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "FAIL: settings still not applicable after ${i} attempts. Try re-running apply-settings.py." >&2
    exit 1
  fi
  sleep 2
done

# --- 9. final, verbose apply (so the operator sees the green ticks) -----
echo "==> Applying canonical settings"
$APPLY "$repo"

echo
echo "Done. $repo is now public with org-wide settings + branch protection."
