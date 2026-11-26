# Security review

Living reference for the automatic security review:
[`reusable-security-review.yml`](../.github/workflows/reusable-security-review.yml) and the
caller each repo runs it from. Keep this doc current as they change. The rules it checks are
the [security guide](security/README.md); how to report a problem that has already happened is
[`SECURITY.md`](../SECURITY.md).

## What it does

Each job in the workflow checks one rule of the security guide, on every pull request, and
reports its own check, `security / <job>`, so each can be required on its own. A new rule's
check is a new job, and needs no change in any repo.

| Rule | Check | What it does |
|---|---|---|
| [`security/secrets`](security/README.md#secrets) | `security / secrets` | gitleaks scans the pull request's commits against the org's rules and the repo's exceptions; a finding fails the check |

In public repos, the ruleset in [`settings.yml`](../.github/settings.yml) makes `security /
secrets` required, so a pull request with a finding can't merge. Private repos get no ruleset on
GitHub Free, so there the check shows a finding but doesn't block.

## What it needs

| Where | What | Kept in place by |
|---|---|---|
| Each repo | `.github/workflows/security-review.yml`, a copy of [`workflow-templates/security-review.yml`](../workflow-templates/security-review.yml) | [`create-repo.sh`](../scripts/create-repo.sh) commits it to a new repo; the rollout fails a repo without it, or with a changed copy (`required_files` in [`settings.yml`](../.github/settings.yml)) |
| This repo | [`.gitleaks.toml`](../.gitleaks.toml) and [`scripts/fetch-scanner.sh`](../scripts/fetch-scanner.sh), read from `main` at the start of each run | |

## Operating it

**Adding it to an existing repo.** Open a pull request adding a copy of the template.

**Changing a rule.** The review reads `.gitleaks.toml` and `fetch-scanner.sh` from this repo's
`main` at the start of each run, so a merged change applies to the next review in every repo.

**Updating the scanners.** [`fetch-scanner.sh`](../scripts/fetch-scanner.sh) downloads gitleaks
and trufflehog at pinned releases, for the review and `make-public.sh` alike. It checks each
download against the release's checksums file, and that file against a SHA-256 pinned in the
script. Dependabot can't see these pins. To move to a new release, change its version and hash
together:

```bash
gh release download v<version> -R gitleaks/gitleaks -p '*_checksums.txt'
sha256sum gitleaks_<version>_checksums.txt
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `security / secrets` fails: `leaks found` | A commit in the pull request matches a rule | The job's log names the commit, file and line. Rotate a real secret; for a false positive, make an exception ([security guide](security/README.md#secrets)) |
| A pull request can't merge: `security / secrets` is `Expected — Waiting for status to be reported` | No review ran on the latest commit: the repo has no caller, or the run hasn't started | Check the repo has the caller (the rollout reports it), and that Actions ran on that push |
| The rollout reports `FAIL file '.github/workflows/security-review.yml': could not read: ... (HTTP 404)` | The repo has no caller | A pull request adding it |
| The rollout reports `differs from workflow-templates/security-review.yml` | The repo's caller was edited | A pull request restoring the template's copy, or a change to the template if every repo should have it |
| `FAIL: <scanner>_<version>_checksums.txt doesn't match the SHA-256 pinned in ...` | The release's checksums file isn't the one that was pinned: the release was republished, or tampered with | Find out which before changing the pinned hash |
| `FAIL: <asset> doesn't match <checksums file>` | The download was corrupted or replaced | Re-run; if it persists, treat it as tampering |
