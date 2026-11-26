# Security review

Living reference for the org's security rules and the automatic security review that checks
them: [`reusable-security-review.yml`](../.github/workflows/reusable-security-review.yml) and
the caller each repo runs it from. Keep this doc current as they change. A security problem
that does reach a repo is reported privately, through the repo's Security tab, not in a public
issue.

## What it does

Each job in the workflow checks one rule, and reports its own check, `security / <job>`, so
each can be required on its own. A new rule's check is a new job, and needs no change in any
repo.

| Rule | Check | What it does |
|---|---|---|
| [No secrets in the code](#no-secrets-in-the-code) | `security / secrets` | gitleaks scans the pull request's commits; a finding fails the check |

## No secrets in the code

Credentials, keys and tokens are never committed: `.env` files, service-account keys and the
like are gitignored ([CONTRIBUTING.md → Secrets & data](../CONTRIBUTING.md#secrets--data)).
Four things check for them:

| When | What | Where |
|---|---|---|
| A push | GitHub's push protection rejects a push that carries a recognised secret | Public repos |
| Any commit | GitHub's secret scanning raises an alert on the Security tab | Public repos |
| Each pull request | `security / secrets`: gitleaks scans the pull request's commits | Every repo with the caller |
| Before a repo goes public | [`make-public.sh`](../scripts/make-public.sh) scans every branch's whole history with its own patterns, gitleaks and trufflehog, and won't flip the repo on a finding | The repo being promoted |

GitHub Free doesn't offer secret scanning or push protection to private repos, so there the
pull request scan is the only check on new commits. [`settings.yml`](../.github/settings.yml)
turns both on in public repos, and the rollout turns them back on if they're turned off.

**Rules and exceptions.** gitleaks uses the org's rules, [`.gitleaks.toml`](../.gitleaks.toml):
its default rules, plus anything added there. Change that file for something every repo should
share. A false positive in one repo is that repo's exception, made in a pull request so it's
reviewed:

- the finding's fingerprint, which gitleaks prints, on a line of the repo's `.gitleaksignore`;
- or a `gitleaks:allow` comment on the line, or `trufflehog:ignore` for trufflehog, which runs
  only in `make-public.sh`.

`make-public.sh` reports how many findings a repo's `.gitleaksignore` suppresses, so they're
seen again before the repo goes public.

A real secret is never an exception. Rotate it: it's in the branch's history, so a commit that
removes it doesn't make it safe.

## What it needs

| Where | What | Kept in place by |
|---|---|---|
| Each repo | `.github/workflows/security-review.yml`, a copy of [`workflow-templates/security-review.yml`](../workflow-templates/security-review.yml) | [`create-repo.sh`](../scripts/create-repo.sh) commits it to a new repo |
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
| `security / secrets` fails: `leaks found` | A commit in the pull request matches a rule | The job's log names the commit, file and line. Rotate a real secret; for a false positive, make an exception as above |
| `FAIL: <scanner>_<version>_checksums.txt doesn't match the SHA-256 pinned in ...` | The release's checksums file isn't the one that was pinned: the release was republished, or tampered with | Find out which before changing the pinned hash |
| `FAIL: <asset> doesn't match <checksums file>` | The download was corrupted or replaced | Re-run; if it persists, treat it as tampering |
