"""Apply SwimBlocks org-wide repo settings to one or more repos.

Reads `.github/settings.yml` (Probot "Settings" app shape) and PATCHes the
repository settings via the GitHub REST API using `gh`. Used by the `rollout`
workflow across the whole org, and by `scripts/create-repo.sh` at new-repo
creation time.

Usage:
    python scripts/apply_settings.py owner/repo [owner/repo ...]

Inside the rollout workflow, where --version both records the tag on each repo
as the `settings_version` custom property and names it in the job summary:

    python scripts/apply_settings.py --version TAG --summary-file FILE owner/repo

Requires the `gh` CLI authenticated with a token that has admin rights on the
target repo(s), plus Custom properties write to record the version. Inside the
rollout workflow that is a GitHub App installation token; locally it is your
usual `gh auth login`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

# Only fields under `repository:` that we know how to PATCH via
# `PATCH /repos/{owner}/{repo}`. Anything else in the YAML is left for a
# future iteration (collaborators and Probot Settings' other top-level
# sections); `branches`, `rulesets` and `labels` have their own handling below.
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


def gh_error(exc: subprocess.CalledProcessError) -> str:
    """The message `gh` produced, for appending to a failure line.

    Every call whose failure is reported through this must pass
    `stderr=subprocess.PIPE`; otherwise the cause is thrown away and the
    operator gets a bare exit code — see
    https://github.com/swimblocks/.github/issues/49. Capturing also keeps gh's
    unbuffered stderr out of the log, where it would otherwise appear seconds
    ahead of the buffered stdout line that explains it. Only the last stderr
    line is kept: that is the `gh: ... (HTTP 403)` summary, not the noise above.
    """
    lines = [ln for ln in (exc.stderr or "").strip().splitlines() if ln.strip()]
    return f": {lines[-1].strip()}" if lines else f" (exit {exc.returncode})"


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
        print("  (no PATCHable settings — nothing to do)")
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


# ---------------------------------------------------------------------------
# Labels
#
# Create-if-missing, and nothing else. The values here seed a new label; they do
# not govern an existing one. A repo that recolours its labels to group them
# visually is doing something useful, and a weekly job reverting that would be
# churn — colour carries no policy weight. What does carry weight is that the
# label *exists*, since a PR cannot be given a label the repo doesn't have.
#
# Nor are unlisted labels removed: repos carry GitHub's defaults and the ones
# Dependabot creates, and deleting a label strips it from every issue and PR
# that used it. `settings.yml` is the minimum set, not the whole set.
# ---------------------------------------------------------------------------

def normalize_color(value: str | None) -> str:
    """GitHub stores label colours as six lowercase hex digits with no '#'."""
    return str(value or "").lstrip("#").lower()


def list_labels(repo: str) -> dict[str, dict]:
    """Every label on *repo*, keyed by lowercased name.

    GitHub treats label names case-insensitively, so the key is lowercased to
    stop a `No-Issue` on the repo reading as missing against a `no-issue` here.
    """
    # `--jq .[]` emits one compact object per line, which pages cleanly;
    # `--paginate` alone would concatenate raw JSON arrays.
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/labels", "--paginate", "--jq", ".[]"],
        check=True, capture_output=True, text=True,
    ).stdout
    labels = [json.loads(line) for line in out.splitlines() if line.strip()]
    return {label["name"].lower(): label for label in labels}


def missing_labels(desired: list[dict], actual: dict[str, dict]) -> list[dict]:
    """The entries of *desired* that *actual* has no label for."""
    return [d for d in desired if d.get("name") and d["name"].lower() not in actual]


def apply_labels(repo: str, labels_block: list[dict]) -> bool:
    """Create any label in *labels_block* the repo lacks. Returns False on failure."""
    if not labels_block:
        return True
    try:
        actual = list_labels(repo)
    except subprocess.CalledProcessError as e:
        print(f"  FAIL labels: could not list{gh_error(e)}")
        return False

    ok = True
    for desired in missing_labels(labels_block, actual):
        name = desired["name"]
        try:
            subprocess.run(
                ["gh", "api", "-X", "POST", f"repos/{repo}/labels",
                 "-f", f"name={name}",
                 "-f", f"color={normalize_color(desired.get('color'))}",
                 "-f", f"description={desired.get('description') or ''}"],
                check=True, stdout=subprocess.DEVNULL,
            )
            print(f"  OK  label '{name}': created")
        except subprocess.CalledProcessError as e:
            print(f"  FAIL label '{name}': create failed{gh_error(e)}")
            ok = False
    return ok


def verify_labels(repo: str, labels_block: list[dict]) -> bool:
    """Re-read the labels and confirm each one exists.

    Presence is the whole assertion — this only ever creates — so checking
    presence checks everything claimed. (Contrast `verify_ruleset`, where the
    rules are the substance and go unchecked: https://github.com/swimblocks/.github/issues/45)
    """
    if not labels_block:
        return True
    try:
        actual = list_labels(repo)
    except subprocess.CalledProcessError as e:
        print(f"  FAIL labels: could not list{gh_error(e)}")
        return False

    ok = True
    for desired in labels_block:
        name = desired.get("name")
        if not name:
            continue
        if name.lower() in actual:
            print(f"  OK  label '{name}': present")
        else:
            print(f"  FAIL label '{name}': missing")
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Actions secrets
#
# GitHub Free doesn't give private repos the org's Actions secrets, so the
# rollout copies the ones `actions_secrets:` lists into every repo. Each value
# is read from the environment variable of the same name, which rollout.yml
# fills from swimblocks/.github's own secrets.
# ---------------------------------------------------------------------------

def secret_values(
    secrets_block: list[dict], env: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """The value for each listed secret from *env*, and the names *env* lacks."""
    values: dict[str, str] = {}
    missing: list[str] = []
    for entry in secrets_block:
        name = entry.get("name")
        if not name:
            continue
        value = env.get(name, "")
        if value:
            values[name] = value
        else:
            missing.append(name)
    return values, missing


def apply_secrets(repo: str, values: dict[str, str]) -> bool:
    """Set each secret in *values* on *repo*. Returns False on failure.

    The value goes to `gh secret set` on stdin, never on the command line, and
    is never printed. A secret can't be read back, so it is written every run
    rather than compared, and verify_secrets checks only that it exists.
    """
    ok = True
    for name, value in values.items():
        try:
            subprocess.run(
                ["gh", "secret", "set", name, "--repo", repo, "--app", "actions"],
                input=value, text=True,
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            print(f"  OK  secret '{name}': set")
        except subprocess.CalledProcessError as e:
            print(f"  FAIL secret '{name}': set failed{gh_error(e)}")
            ok = False
    return ok


def verify_secrets(repo: str, names: list[str]) -> bool:
    """Confirm each secret in *names* exists on *repo*."""
    if not names:
        return True
    try:
        out = subprocess.run(
            ["gh", "secret", "list", "--repo", repo, "--app", "actions",
             "--json", "name", "--jq", ".[].name"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        print(f"  FAIL secrets: could not list{gh_error(e)}")
        return False
    present = set(out.split())
    ok = True
    for name in names:
        if name in present:
            print(f"  OK  secret '{name}': present")
        else:
            print(f"  FAIL secret '{name}': missing")
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Required files
#
# Every repo carries a copy of each file `required_files:` lists, such as the
# readability review's caller. The rollout checks that the copy is on the
# default branch and matches its source in this repo, and reports a FAIL if
# not. It never writes one: the reconciler has Contents read, not write, as it
# is installed on every repo (docs/reconciler.md). scripts/create-repo.sh adds
# them to a new repo.
# ---------------------------------------------------------------------------

def same_file(got: bytes, want: bytes) -> bool:
    """Whether two copies of a text file match, whatever their line endings."""
    return got.replace(b"\r\n", b"\n") == want.replace(b"\r\n", b"\n")


def verify_required_files(repo: str, files_block: list[dict], root: Path) -> bool:
    """Confirm *repo*'s default branch has each listed file, matching its source."""
    ok = True
    for entry in files_block:
        path, source = entry.get("path"), entry.get("source")
        if not path or not source:
            continue
        try:
            out = subprocess.run(
                ["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
                check=True, capture_output=True, text=True,
            ).stdout
        except subprocess.CalledProcessError as e:
            # A 404 is the file missing; a 403 is the token lacking Contents read.
            print(f"  FAIL file '{path}': could not read{gh_error(e)}")
            ok = False
            continue
        if same_file(base64.b64decode(out), (root / source).read_bytes()):
            print(f"  OK  file '{path}': matches {source}")
        else:
            print(f"  FAIL file '{path}': differs from {source}")
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Security and analysis
#
# GitHub's secret scanning and push protection, which `security_and_analysis:`
# turns on in public repos only: they're free there, and GitHub Free doesn't
# offer them to private repos.
# ---------------------------------------------------------------------------

def security_payload(block: dict[str, str]) -> dict:
    """The `PATCH /repos/{repo}` body setting each feature in *block* to its status."""
    return {"security_and_analysis": {
        feature: {"status": status} for feature, status in block.items()}}


def apply_security(repo: str, block: dict[str, str]) -> bool:
    """Set each feature in *block* on *repo*. Returns False on failure."""
    try:
        subprocess.run(
            ["gh", "api", "-X", "PATCH", f"repos/{repo}", "--input", "-"],
            input=json.dumps(security_payload(block)), text=True,
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        print(f"  FAIL security_and_analysis: PATCH failed{gh_error(e)}")
        return False
    return True


def verify_security(repo: str, block: dict[str, str]) -> bool:
    """Confirm each feature in *block* has its status on *repo*."""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq", ".security_and_analysis // {}"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        print(f"  FAIL security_and_analysis: could not read back{gh_error(e)}")
        return False
    actual = json.loads(out)
    ok = True
    for feature, want in block.items():
        got = (actual.get(feature) or {}).get("status")
        marker = "OK " if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  {marker} {feature}: {got!r} (expected {want!r})")
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
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE)


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
        print(f"  OK  removed legacy branch protection on '{branch}' "
              f"(superseded by ruleset)")


def apply_branch_protection(repo: str, branch: str, protection: dict) -> None:
    """PUT /repos/{owner}/{repo}/branches/{branch}/protection."""
    payload = {k: v for k, v in protection.items() if k in PROTECTION_KEYS}
    cmd = ["gh", "api", "-X", "PUT",
           f"repos/{repo}/branches/{branch}/protection",
           "--input", "-"]
    subprocess.run(cmd, input=json.dumps(payload), text=True,
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE)


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
            mismatch = {
                k: (got.get(k), v) for k, v in expected.items() if got.get(k) != v
            }
            sub_ok = not mismatch
            marker = "OK " if sub_ok else "FAIL"
            print(f"  {marker} branches.{branch}.{key}: "
                  f"{ {k: got.get(k) for k in expected} } (expected {expected})")
            if not sub_ok:
                ok = False
        else:
            sub_ok = got == expected
            marker = "OK " if sub_ok else "FAIL"
            print(f"  {marker} branches.{branch}.{key}: {got!r} "
                  f"(expected {expected!r})")
            if not sub_ok:
                ok = False
    return ok


# ---------------------------------------------------------------------------
# Settings version
#
# The run summary below says what one rollout did. The custom property says what
# state a repo is *in*, which is the question the summary can't answer: with a
# value on every repo, "which repos are behind" is one org-wide query rather than
# a trawl through run logs. See https://github.com/swimblocks/.github/issues/53.
#
# `PATCH /repos/{owner}/{repo}/properties/values` is the only endpoint the
# repository-level "Custom properties" permission grants, which is why the write
# goes per repo rather than through `PATCH /orgs/{org}/properties/values`: the
# org-level equivalent rides on the *organization* Custom properties permission,
# which also carries the schema — create, update and delete of every property
# definition in the org. The narrow grant is worth the extra calls.
#
# The property must already be defined at org level; defining it is a one-time
# org-owner action, deliberately not something this token can do. Until it is,
# every write 422s and the run goes red — which is the right signal, since
# neither that nor a missing permission is a state to sit in. Runbook and the
# drift query: docs/reconciler.md.
# ---------------------------------------------------------------------------

SETTINGS_VERSION_PROPERTY = "settings_version"


def version_payload(version: str) -> dict:
    """The PATCH body recording *version* against SETTINGS_VERSION_PROPERTY."""
    return {
        "properties": [
            {"property_name": SETTINGS_VERSION_PROPERTY, "value": version}
        ]
    }


def set_settings_version(repo: str, version: str) -> bool:
    """Record *version* on *repo*. Returns False on failure."""
    try:
        subprocess.run(
            ["gh", "api", "-X", "PATCH", f"repos/{repo}/properties/values",
             "--input", "-"],
            input=json.dumps(version_payload(version)), text=True,
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        # Two causes, and gh's own message separates them: a 422 means
        # `settings_version` isn't defined on the org yet, a 403 means this
        # token lacks Custom properties write. Both are setup gaps, so both
        # count as failures rather than being skipped.
        print(f"  FAIL {SETTINGS_VERSION_PROPERTY}: PATCH failed{gh_error(e)}")
        return False
    print(f"  OK  {SETTINGS_VERSION_PROPERTY}: {version}")
    return True


# ---------------------------------------------------------------------------
# Run summary
#
# Nothing on a repo records which settings version it is on, so a rollout leaves
# no trace anyone can query afterwards — `officials-admin` sat unreconciled until
# somebody noticed by hand. The table below makes the run itself the record: the
# release it names plus the run history say which repos got which version.
# ---------------------------------------------------------------------------

def summary_table(version: str, repos: list[str], failures: list[str]) -> str:
    """A markdown table of repo -> result -> version, for the job summary."""
    failed = set(failures)
    heading = f"## Settings rollout — `{version}`" if version else "## Settings rollout"
    lines = [heading, "", "| Repo | Result | Version |", "|---|---|---|"]
    for repo in repos:
        result = "FAIL — drift remains" if repo in failed else "OK — applied"
        lines.append(f"| `{repo}` | {result} | `{version or 'unversioned'}` |")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="apply_settings.py",
        description="Apply .github/settings.yml to one or more repos.",
    )
    parser.add_argument("repos", nargs="+", metavar="owner/repo")
    parser.add_argument(
        "--version", default="",
        help="Settings release tag being rolled out. Recorded on each repo as "
             "the settings_version custom property, and named in the summary.",
    )
    parser.add_argument(
        "--require-secrets", action="store_true",
        help="Fail a repo when a secret settings.yml lists has no value in the "
             "environment. The rollout sets this; a local run, which has no "
             "secrets to copy, skips them instead.",
    )
    parser.add_argument(
        "--summary-file",
        help="Append the run summary table to this file (e.g. $GITHUB_STEP_SUMMARY).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    if not shutil.which("gh"):
        print("error: gh CLI not on PATH", file=sys.stderr)
        return 2
    opts = parse_args(argv[1:])

    settings_path = Path(__file__).resolve().parents[1] / ".github" / "settings.yml"
    settings = load_settings(settings_path)
    repo_block = (settings.get("repository") or {})
    branches_block = (settings.get("branches") or [])
    args = patch_args(repo_block)

    rulesets_block = settings.get("rulesets") or []
    labels_block = settings.get("labels") or []
    secret_vals, secrets_missing = secret_values(
        settings.get("actions_secrets") or [], dict(os.environ))
    files_block = settings.get("required_files") or []
    security_block = settings.get("security_and_analysis") or {}

    failures: list[str] = []
    for repo in opts.repos:
        print(f"=== {repo} ===")
        apply(repo, args)
        if not verify(repo, repo_block):
            failures.append(repo)

        # Labels do not depend on visibility — private repos get them too.
        if labels_block:
            # Verify only if applying got far enough to be worth checking —
            # otherwise a failed listing is reported twice for one failure.
            labels_ok = apply_labels(repo, labels_block)
            if labels_ok:
                labels_ok = verify_labels(repo, labels_block)
            if not labels_ok and repo not in failures:
                failures.append(repo)

        # Secrets too: private repos are the reason they're copied at all.
        if secrets_missing:
            if opts.require_secrets:
                print(f"  FAIL secrets: no value in the environment for "
                      f"{', '.join(secrets_missing)}")
                if repo not in failures:
                    failures.append(repo)
            else:
                print(f"  SKIP secrets: no value in the environment for "
                      f"{', '.join(secrets_missing)}; the rollout copies them")
        if secret_vals:
            secrets_ok = apply_secrets(repo, secret_vals)
            if secrets_ok:
                secrets_ok = verify_secrets(repo, list(secret_vals))
            if not secrets_ok and repo not in failures:
                failures.append(repo)

        # And files: a private repo's review needs its caller as much as a public one's.
        if files_block and not verify_required_files(
                repo, files_block, settings_path.parents[1]):
            if repo not in failures:
                failures.append(repo)

        is_public = get_repo_visibility(repo) == "public"

        if is_public and security_block:
            security_ok = apply_security(repo, security_block)
            if security_ok:
                security_ok = verify_security(repo, security_block)
            if not security_ok and repo not in failures:
                failures.append(repo)

        if is_public and rulesets_block:
            # Public repos: rulesets with bypass actors for admin force-push
            # break-glass. Legacy branch protection is removed so it can't
            # silently override the ruleset.
            for ruleset in rulesets_block:
                try:
                    apply_ruleset(repo, ruleset)
                    if not verify_ruleset(repo, ruleset["name"]):
                        if repo not in failures:
                            failures.append(repo)
                except subprocess.CalledProcessError as e:
                    print(f"  SKIP ruleset '{ruleset.get('name')}': apply failed"
                          f"{gh_error(e)}")
                    if repo not in failures:
                        failures.append(repo)
            for entry in branches_block:
                branch = entry.get("name")
                if branch:
                    delete_legacy_protection(repo, branch)
        else:
            # Private repos: attempt legacy branch protection (expected to fail
            # on the Free plan).
            for entry in branches_block:
                branch = entry.get("name")
                protection = entry.get("protection") or {}
                if not branch or not protection:
                    continue
                try:
                    apply_branch_protection(repo, branch, protection)
                except subprocess.CalledProcessError as e:
                    # Expected on GitHub Free: private repos can't have branch
                    # protection. This is a documented known limitation, not a
                    # failure — the repo stays aligned on every merge-method
                    # field. Skip without failing the run. (If the plan is later
                    # upgraded, the PUT succeeds and verify below applies.)
                    #
                    # Report gh's own message rather than asserting the cause:
                    # a 403 from the token lacking Administration write looks
                    # identical from here, and claiming the plan limitation for
                    # it would send the reader down the wrong path.
                    print(f"  SKIP branches.{branch}: PUT failed{gh_error(e)}. "
                          f"Merge-method settings above still applied. The Pro/"
                          f"visibility 403 is the expected plan limit on a "
                          f"private repo; any other error is not.")
                    continue
                if not verify_branch_protection(repo, branch, protection):
                    if repo not in failures:
                        failures.append(repo)

        # Last, and only for a repo that came through clean: the value means
        # "this repo was taken through the whole of settings.yml at this tag",
        # so a repo that still has drift must not claim it. Leaving it unstamped
        # is what keeps it in the drift query's output until someone fixes it.
        #
        # Without --version there is no release to name — create-repo.sh applies
        # whatever is on main, and claiming a tag for that would be a lie. Such a
        # repo gets its value from the rollout its repo-created dispatch starts.
        if opts.version:
            if repo in failures:
                print(f"  SKIP {SETTINGS_VERSION_PROPERTY}: not recorded, "
                      f"drift remains above")
            elif not set_settings_version(repo, opts.version):
                failures.append(repo)

    if opts.summary_file:
        with open(opts.summary_file, "a", encoding="utf-8") as f:
            f.write(summary_table(opts.version, opts.repos, failures))

    if failures:
        print(f"\nFAIL: drift remains on {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
