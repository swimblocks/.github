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
# scripts/apply_settings.py. The result is verified before exit. Note: a
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

# Adding the org's workflow callers below creates files under .github/workflows, which needs
# the token's workflow scope. Check before creating anything, so a missing scope can't
# leave a repo created but not set up. A token that reports no scopes (fine-grained, or an
# app's) is left to the call itself.
scopes=$(gh api -i user 2>/dev/null | tr -d '\r' | sed -n 's/^[Xx]-[Oo][Aa]uth-[Ss]copes: //p')
if [ -n "$scopes" ] && ! grep -qw workflow <<<"${scopes//,/ }"; then
  echo "error: your gh token lacks the workflow scope, needed to add the org's workflow" >&2
  echo "       callers. Add it with: gh auth refresh -s workflow" >&2
  exit 1
fi

echo "==> Creating $REPO"
gh repo create "$REPO" $visibility_flag "$@"

# GitHub sometimes lags a moment between create and ready-to-PATCH.
for _ in 1 2 3 4 5; do
  if gh api "repos/$REPO" >/dev/null 2>&1; then break; fi
  sleep 1
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The org's workflow callers go in as the repo's first commits, before anyone opens a pull
# request: Claude Code Action runs only once the readability review's caller is on the default
# branch. The settings check below confirms the ones settings.yml's required_files lists.
# Carriage returns are dropped, so a Windows checkout's copy matches the template's.
add_caller() {
  local name=$1 message=$2
  echo "==> Adding the $name caller"
  gh api -X PUT "repos/$REPO/contents/.github/workflows/$name.yml" \
    -f message="$message" \
    -f content="$(tr -d '\r' < "$SCRIPT_DIR/../workflow-templates/$name.yml" | base64 | tr -d '\n')" \
    >/dev/null
}
add_caller readability-review "Call the org's readability review"
add_caller secret-scan "Call the org's secret scan"

echo "==> Applying canonical settings"
python "$SCRIPT_DIR/apply_settings.py" "$REPO"

echo
echo "Done. $REPO is live with org-wide defaults."
echo "Clone it into the standard local layout: ghq get https://github.com/$REPO"
echo "Next: add per-repo CI calling the shared workflow for the repo's language:"
echo "        Python: uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main"
echo "        Go:     uses: swimblocks/.github/.github/workflows/reusable-go-ci.yml@main"
echo "      (a Go repo starts on the current stable Go release, named by go.mod's go directive),"
echo "      add a per-repo .github/dependabot.yml, draft an AGENTS.md."
echo "The readability review's and secret scan's callers are already on the default branch."
echo "When ready to release publicly: scripts/make-public.sh $REPO"
