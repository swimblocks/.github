#!/usr/bin/env bash
# Install user-local SwimBlocks agent pointer files.
#
# Writes three small files that let any AI coding agent invoked from outside a
# specific repo still pick up the canonical SwimBlocks rules:
#
#   ~/src/AGENTS.md                              cross-everything pointer
#   ~/src/github.com/swimblocks/AGENTS.md        org-scope pointer
#   ~/src/github.com/swimblocks/CLAUDE.md        Claude Code @import
#
# Each file is a pointer at the canonical content in your local clone of the
# standards repo (~/src/github.com/swimblocks/.github/AGENTS.md). Updating the
# canonical content is just `git pull` in the standards repo; the pointer
# files never need to change.
#
# Usage:
#   bash scripts/install-local-agent-files.sh [--dry-run] [--force]
#
# Flags:
#   --dry-run   Print what would be written without touching the filesystem.
#   --force     Overwrite existing pointer files (default is to leave them alone).
#
# See docs/development.md for the bigger picture.
set -euo pipefail

dry_run=0
force=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --force)   force=1 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# Resolve the ghq root. Prefer `git config --global ghq.root`; fall back to ~/src,
# which is the SwimBlocks-recommended default.
ghq_root="$(git config --global --get ghq.root 2>/dev/null || true)"
if [ -z "$ghq_root" ]; then
  ghq_root="$HOME/src"
fi
# Expand a leading ~ if the config stores it that way.
ghq_root="${ghq_root/#\~/$HOME}"

# Canonical clone of the standards repo. The pointer files refer to it.
standards_repo="$ghq_root/github.com/swimblocks/.github"
canonical_agents="$standards_repo/AGENTS.md"

if [ ! -f "$canonical_agents" ]; then
  cat >&2 <<EOM
error: canonical AGENTS.md not found at:
  $canonical_agents

Clone the standards repo first:
  ghq get https://github.com/swimblocks/.github
or
  git clone https://github.com/swimblocks/.github "$standards_repo"
EOM
  exit 1
fi

# ---------------------------------------------------------------------------
# File contents (small enough to inline; matches docs/development.md).
# ---------------------------------------------------------------------------

cross_everything_path="$ghq_root/AGENTS.md"
cross_everything_content="$(cat <<EOF
# Agents in ~/src

This file is read by any AI coding agent invoked anywhere under \`$ghq_root\`.

Work in any **SwimBlocks** repo (anything under \`$ghq_root/github.com/swimblocks/\`) follows the
SwimBlocks shared standards. The canonical entry point lives in your local clone of the
standards repo:

  $standards_repo/AGENTS.md
  $standards_repo/CONTRIBUTING.md

Read those first. Highlights:

- Open a GitHub issue before doing any non-trivial work.
- Branch \`<issue-number>-<short-slug>\`. One issue, one branch, one PR.
- PR title becomes the squash commit subject; PR body becomes the squash commit message.
- Agents hand off after CI green; never self-merge (large mechanical org-wide changes
  excepted, by prior agreement).
- TODO / aspirational comments must link to a GitHub issue, not float as bare wishes.

Work outside SwimBlocks (other repos under \`$ghq_root\`, or scratch files at the top level)
follows whatever rules those repos define.
EOF
)"

org_pointer_path="$ghq_root/github.com/swimblocks/AGENTS.md"
org_pointer_content="$(cat <<EOF
# SwimBlocks org

Any agent invoked under \`$ghq_root/github.com/swimblocks/\` should follow the canonical
SwimBlocks agent guide:

  $standards_repo/AGENTS.md

Full development standards live in:

  $standards_repo/CONTRIBUTING.md

Updates flow in via \`git pull\` in the standards repo. This file is a pointer; it
intentionally carries no rules of its own.
EOF
)"

claude_pointer_path="$ghq_root/github.com/swimblocks/CLAUDE.md"
claude_pointer_content="$(cat <<EOF
# Claude Code — SwimBlocks org

The canonical SwimBlocks rules live in the standards repo. Import them:

@$standards_repo/AGENTS.md

Long-form house rules:

@$standards_repo/CONTRIBUTING.md
EOF
)"

# ---------------------------------------------------------------------------
# Install loop.
# ---------------------------------------------------------------------------

install_one() {
  local path=$1 content=$2 label=$3
  if [ -e "$path" ] && [ "$force" -eq 0 ]; then
    echo "SKIP  $label  ($path — exists; rerun with --force to overwrite)"
    return
  fi
  if [ "$dry_run" -eq 1 ]; then
    echo "WOULD WRITE  $label  ($path)"
    return
  fi
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$content" > "$path"
  echo "WROTE  $label  ($path)"
}

echo "ghq root:        $ghq_root"
echo "standards repo:  $standards_repo"
if [ "$dry_run" -eq 1 ]; then echo "(dry run — nothing will be written)"; fi
echo

install_one "$cross_everything_path" "$cross_everything_content" "~/src/AGENTS.md"
install_one "$org_pointer_path"      "$org_pointer_content"      "~/src/github.com/swimblocks/AGENTS.md"
install_one "$claude_pointer_path"   "$claude_pointer_content"   "~/src/github.com/swimblocks/CLAUDE.md"

echo
if [ "$dry_run" -eq 1 ]; then
  echo "Done (dry run). Re-run without --dry-run to install."
else
  echo "Done. Pull the standards repo to refresh the canonical content."
fi
