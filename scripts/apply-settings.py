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


# Top-level keys of the branch protection PUT body. Anything not in this set is
# rejected by the API, so we filter `protection:` in the YAML down to these.
PROTECTION_KEYS = {
    "required_status_checks", "enforce_admins", "required_pull_request_reviews",
    "restrictions", "required_linear_history", "allow_force_pushes",
    "allow_deletions", "required_conversation_resolution", "lock_branch",
    "allow_fork_syncing", "block_creations",
}


def get_repo_visibility(repo: str) -> str:
    """Return 'public' or 'private' for the repo."""
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}", "--jq", ".visibility"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().lower()
    return out


def list_rulesets(repo: str) -> list[dict]:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/rulesets"],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def apply_ruleset(repo: str, ruleset: dict) -> None:
    """Create or update a named ruleset (idempotent by name)."""
    existing = list_rulesets(repo)
    match = next((r for r in existing if r["name"] == ruleset["name"]), None)
    if match:
        cmd = ["gh", "api", "-X", "PUT",
               f"repos/{repo}/rulesets/{match['id']}",
               "--input", "-"]
    else:
        cmd = ["gh", "api", "-X", "POST",
               f"repos/{repo}/rulesets",
               "--input", "-"]
    subprocess.run(cmd, input=json.dumps(ruleset), text=True,
                   check=True, stdout=subprocess.DEVNULL)


def verify_ruleset(repo: str, ruleset_name: str) -> bool:
    existing = list_rulesets(repo)
    found = any(r["name"] == ruleset_name for r in existing)
    marker = "OK " if found else "FAIL"
    print(f"  {marker} ruleset '{ruleset_name}': {'present' if found else 'missing'}")
    return found


def delete_legacy_protection(repo: str, branch: str) -> None:
    """Remove legacy branch protection (superseded by ruleset on public repos)."""
    result = subprocess.run(
        ["gh", "api", "-X", "DELETE",
         f"repos/{repo}/branches/{branch}/protection"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  OK  removed legacy branch protection on '{branch}' (superseded by ruleset)")


def apply_branch_protection(repo: str, branch: str, protection: dict) -> None:
    """PUT /repos/{owner}/{repo}/branches/{branch}/protection."""
    payload = {k: v for k, v in protection.items() if k in PROTECTION_KEYS}
    cmd = ["gh", "api", "-X", "PUT",
           f"repos/{repo}/branches/{branch}/protection",
           "--input", "-"]
    subprocess.run(cmd, input=json.dumps(payload), text=True,
                   check=True, stdout=subprocess.DEVNULL)


def _flatten_protection(actual: dict) -> dict:
    """The GET response wraps several fields as {enabled: bool}. Flatten so we
    can compare against the YAML."""
    flat: dict = {}
    for key in PROTECTION_KEYS:
        if key not in actual:
            flat[key] = None
            continue
        val = actual[key]
        # Boolean-enabled wrappers: {url?, enabled: bool}
        if isinstance(val, dict) and set(val.keys()) <= {"url", "enabled"}:
            flat[key] = val.get("enabled", False)
        else:
            flat[key] = val
    return flat


def verify_branch_protection(repo: str, branch: str, protection: dict) -> bool:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/branches/{branch}/protection"],
        check=True, capture_output=True, text=True,
    ).stdout
    actual_flat = _flatten_protection(json.loads(out))
    ok = True
    for key, expected in protection.items():
        if key not in PROTECTION_KEYS:
            continue
        got = actual_flat.get(key)
        if isinstance(expected, dict) and isinstance(got, dict):
            mismatch = {k: (got.get(k), v) for k, v in expected.items() if got.get(k) != v}
            sub_ok = not mismatch
            marker = "OK " if sub_ok else "FAIL"
            print(f"  {marker} branches.{branch}.{key}: "
                  f"{ {k: got.get(k) for k in expected} } (expected {expected})")
            if not sub_ok:
                ok = False
        else:
            sub_ok = got == expected
            marker = "OK " if sub_ok else "FAIL"
            print(f"  {marker} branches.{branch}.{key}: {got!r} (expected {expected!r})")
            if not sub_ok:
                ok = False
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
    branches_block = (settings.get("branches") or [])
    args = patch_args(repo_block)

    rulesets_block = settings.get("rulesets") or []

    failures: list[str] = []
    for repo in argv[1:]:
        print(f"=== {repo} ===")
        apply(repo, args)
        if not verify(repo, repo_block):
            failures.append(repo)

        is_public = get_repo_visibility(repo) == "public"

        if is_public and rulesets_block:
            # Public repos: rulesets with bypass actors for admin force-push break-glass.
            # Legacy branch protection is removed so it can't silently override the ruleset.
            for ruleset in rulesets_block:
                try:
                    apply_ruleset(repo, ruleset)
                    if not verify_ruleset(repo, ruleset["name"]):
                        if repo not in failures:
                            failures.append(repo)
                except subprocess.CalledProcessError as e:
                    print(f"  SKIP ruleset '{ruleset.get('name')}': apply failed "
                          f"(exit {e.returncode}).")
                    if repo not in failures:
                        failures.append(repo)
            for entry in branches_block:
                branch = entry.get("name")
                if branch:
                    delete_legacy_protection(repo, branch)
        else:
            # Private repos: attempt legacy branch protection (expected to fail on Free plan).
            for entry in branches_block:
                branch = entry.get("name")
                protection = entry.get("protection") or {}
                if not branch or not protection:
                    continue
                try:
                    apply_branch_protection(repo, branch, protection)
                except subprocess.CalledProcessError as e:
                    print(f"  SKIP branches.{branch}: PUT failed (exit {e.returncode}). "
                          f"Likely cause: private repo on a plan without branch "
                          f"protection, or the branch doesn't exist yet.")
                    if repo not in failures:
                        failures.append(repo)
                    continue
                if not verify_branch_protection(repo, branch, protection):
                    if repo not in failures:
                        failures.append(repo)
    if failures:
        print(f"\nFAIL: drift remains on {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
