#!/usr/bin/env python3
"""Apply SwimBlocks org-wide repo settings to one or more repos.

Reads `.github/settings.yml` (Probot "Settings" app shape) and PATCHes the
repository settings via the GitHub REST API using `gh`. Used by both the
scheduled reconciler workflow and by `scripts/create-repo.sh` at new-repo
creation time.

Usage:
    python scripts/apply-settings.py owner/repo [owner/repo ...]

Requires the `gh` CLI authenticated with a token that has admin rights on
the target repo(s). Inside the reconciler workflow that's
`SWIMBLOCKS_ADMIN_TOKEN`; locally it's your usual `gh auth login`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# Only fields under `repository:` that we know how to PATCH via
# `PATCH /repos/{owner}/{repo}`. Anything else in the YAML is left for a
# future iteration (branches, labels, collaborators — Probot Settings'
# other top-level sections).
PATCHABLE = {
    "allow_squash_merge",
    "allow_merge_commit",
    "allow_rebase_merge",
    "squash_merge_commit_title",
    "squash_merge_commit_message",
    "merge_commit_title",
    "merge_commit_message",
    "delete_branch_on_merge",
    "allow_update_branch",
    "allow_auto_merge",
    "has_issues",
    "has_projects",
    "has_wiki",
}


def load_settings(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def patch_args(repo_block: dict) -> list[str]:
    """Translate the `repository:` block into `gh api -F/-f` flags."""
    args: list[str] = []
    for key, value in repo_block.items():
        if key not in PATCHABLE:
            continue
        if isinstance(value, bool):
            args.extend(["-F", f"{key}={'true' if value else 'false'}"])
        else:
            args.extend(["-f", f"{key}={value}"])
    return args


def apply(repo: str, args: list[str]) -> None:
    if not args:
        print(f"  (no PATCHable settings — nothing to do)")
        return
    cmd = ["gh", "api", "-X", "PATCH", f"repos/{repo}", *args]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def verify(repo: str, repo_block: dict) -> bool:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}"],
        check=True, capture_output=True, text=True,
    ).stdout
    actual = json.loads(out)
    ok = True
    for key, expected in repo_block.items():
        if key not in PATCHABLE:
            continue
        got = actual.get(key)
        marker = "OK " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  {marker} {key}: {got!r} (expected {expected!r})")
    return ok


def main(argv: list[str]) -> int:
    if not shutil.which("gh"):
        print("error: gh CLI not on PATH", file=sys.stderr)
        return 2
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    settings_path = Path(__file__).resolve().parents[1] / ".github" / "settings.yml"
    settings = load_settings(settings_path)
    repo_block = (settings.get("repository") or {})
    args = patch_args(repo_block)

    failures: list[str] = []
    for repo in argv[1:]:
        print(f"=== {repo} ===")
        apply(repo, args)
        if not verify(repo, repo_block):
            failures.append(repo)
    if failures:
        print(f"\nFAIL: drift remains on {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
