#!/usr/bin/env bash
# Create a new repo in the SwimBlocks org with the canonical settings applied.
#
# Usage:
#   scripts/create-repo.sh <repo-name> [--private] [--description "..."]
#   scripts/create-repo.sh <repo-name> --public  --description "Short About line"
#
# Defaults to --public if neither flag is given. Any extra flags after the name
# are forwarded straight to `gh repo create` (e.g. --description, --homepage,
# --license, --gitignore).
#
# After creation, the repo's settings are aligned with .github/settings.yml via
# scripts/apply-settings.py. The result is verified before exit.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <repo-name> [--public|--private] [--description \"...\"] [other gh repo create flags]" >&2
  exit 2
fi

name=$1; shift

# Default to public if neither --public nor --private was supplied.
visibility_flag="--public"
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
echo "Remember to: enable branch protection on main, add any per-repo Dependabot/CI as needed."
