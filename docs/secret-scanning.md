# Secret scanning

Living reference for how SwimBlocks repos are scanned for committed secrets. Keep it current as
the scans change. A secret that does get committed is reported privately, through the repo's
Security tab, not in a public issue.

## What runs where

| When | What | Where |
|---|---|---|
| A push | GitHub's push protection rejects a push that carries a recognised secret | Public repos |
| Any commit | GitHub's secret scanning raises an alert on the Security tab | Public repos |
| Each pull request | gitleaks scans the pull request's commits; a finding fails the `secret-scan / gitleaks` check | Every repo with the caller |
| Before a repo goes public | [`make-public.sh`](../scripts/make-public.sh) scans every branch's whole history with its own patterns, gitleaks and trufflehog, and won't flip the repo on a finding | The repo being promoted |

GitHub Free doesn't offer secret scanning or push protection to private repos, so there the
pull request scan is the only check on new commits. [`settings.yml`](../.github/settings.yml)
turns both on in public repos, and the rollout turns them back on if they're turned off.

The pull request scan is
[`reusable-secret-scan.yml`](../.github/workflows/reusable-secret-scan.yml), which each repo
runs from `.github/workflows/secret-scan.yml`, a copy of
[`workflow-templates/secret-scan.yml`](../workflow-templates/secret-scan.yml).
[`create-repo.sh`](../scripts/create-repo.sh) commits it to a new repo. To add it to an existing
one, open a pull request adding a copy of the template.

## Rules and exceptions

gitleaks uses the org's rules, [`.gitleaks.toml`](../.gitleaks.toml): its default rules, plus
anything added there. Change that file for something every repo should share.

A false positive in one repo is that repo's exception, made in a pull request so it's reviewed:

- the finding's fingerprint, which gitleaks prints, on a line of the repo's `.gitleaksignore`;
- or a `gitleaks:allow` comment on the line, or `trufflehog:ignore` for trufflehog, which runs
  only in `make-public.sh`.

`make-public.sh` reports how many findings a repo's `.gitleaksignore` suppresses, so they're
seen again before the repo goes public.

A real secret is never an exception. Rotate it: it's in the branch's history, so a commit that
removes it doesn't make it safe.

## Updating the scanners

[`fetch-scanner.sh`](../scripts/fetch-scanner.sh) downloads both scanners at pinned releases,
for `make-public.sh` and the pull request scan alike. It checks each download against the
release's checksums file, and that file against a SHA-256 pinned in the script. Dependabot
can't see these pins. To move to a new release, change its version and hash together:

```bash
gh release download v<version> -R gitleaks/gitleaks -p '*_checksums.txt'
sha256sum gitleaks_<version>_checksums.txt
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The `secret-scan / gitleaks` check fails: `leaks found` | A commit in the pull request matches a rule | The log names the commit, file and line. Rotate a real secret; for a false positive, make an exception as above |
| `FAIL: <scanner>_<version>_checksums.txt doesn't match the SHA-256 pinned in ...` | The release's checksums file isn't the one that was pinned: the release was republished, or tampered with | Find out which before changing the pinned hash |
| `FAIL: <asset> doesn't match <checksums file>` | The download was corrupted or replaced | Re-run; if it persists, treat it as tampering |
