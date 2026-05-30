#!/usr/bin/env bash
# Create a new repo in the SwimBlocks org with the canonical settings applied.
#
# Usage:
#   scripts/create-repo.sh <repo-name> [--public] [--description "..."]
#   scripts/create-repo.sh <repo-name>             # private by default
#
# Defaults to **private** because SwimBlocks repos usually start that way.
# When you're ready to release a repo, promote it with scripts/make-public.sh
# — that script is the documented place where we accumulate pre-public
# checks (secret scans, required-files audit, branch-protection install).
#
# Any extra flags after the name are forwarded straight to `gh repo create`
# (e.g. --description, --homepage, --license, --gitignore).
#
# After creation, the repo's settings are aligned with .github/settings.yml via
# scripts/apply-settings.py. The result is verified before exit. Note: a
# private repo on GitHub Free can't have branch protection — that part will
# show as SKIP, which is expected and correct until make-public.sh runs.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <repo-name> [--public|--private|--internal] [--description \"...\"] [other gh repo create flags]" >&2
  echo "       (defaults to --private; promote later with make-public.sh)" >&2
  exit 2
fi

name=$1; shift

# Default to private if no visibility flag was supplied.
visibility_flag="--private"
for arg in "$@"; do
  case "$arg" in
    --public|--private|--internal) visibility_flag="" ;;
  esac
done

REPO="swimblocks/$name"
echo "==> Creating $REPO"
gh repo create "$REPO" $visibility_flag "$@"

# GitHub sometimes lags a moment between create and ready-to-PATCH.
for _ in 1 2 3 4 5; do
  if gh api "repos/$REPO" >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> Applying canonical settings"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/apply-settings.py" "$REPO"

echo
echo "Done. $REPO is live with org-wide defaults."
echo "Next: add per-repo CI (uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main),"
echo "      add a per-repo .github/dependabot.yml, draft an AGENTS.md."
echo "When ready to release publicly: scripts/make-public.sh $REPO"
