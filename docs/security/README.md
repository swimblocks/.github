# SwimBlocks security guide

How SwimBlocks code keeps the org's credentials, and the people whose data it handles, safe.
These rules apply in every repo.

**The security review enforces this guide.** Each rule a machine can check has a check in the
[security review](../security-review.md), which runs on every pull request, the way lint
enforces the [style guide](../styleguide/README.md). What's written here is the rule itself,
what checks it, and how a repo makes an exception.

Each rule has an ID, `security/` and its heading (`security/secrets`), so a review comment can
say which rule it applies.

Found a problem that has already happened, such as a leaked credential or exposed personal
data? Report it privately as [`SECURITY.md`](../../SECURITY.md) says, not in a public issue.

## Secrets

Credentials, keys and tokens are never committed. They come from the environment or a secret
store, and the files that hold them locally (`.env`, service-account keys) are gitignored.

Four things check for them:

| When | What | Where |
|---|---|---|
| A push | GitHub's push protection rejects a push that carries a recognised secret | Public repos |
| Any commit | GitHub's secret scanning raises an alert on the Security tab | Public repos |
| Each pull request | The security review's `security / secrets` check: gitleaks scans the pull request's commits | Every repo |
| Before a repo goes public | [`make-public.sh`](../../scripts/make-public.sh) scans every branch's whole history with its own patterns, gitleaks and trufflehog, and won't flip the repo on a finding | The repo being promoted |

GitHub Free doesn't offer secret scanning or push protection to private repos, so there the
security review is the only check on new commits. [`settings.yml`](../../.github/settings.yml)
turns both on in public repos.

gitleaks uses the org's rules, [`.gitleaks.toml`](../../.gitleaks.toml): its default rules,
plus anything added there. Change that file for something every repo should share.

**Exceptions.** A false positive in one repo is that repo's exception, made in a pull request
so it's reviewed:

- the finding's fingerprint, which gitleaks prints, on a line of the repo's `.gitleaksignore`;
- or a `gitleaks:allow` comment on the line, or `trufflehog:ignore` for trufflehog, which runs
  only in `make-public.sh`.

`make-public.sh` reports how many findings a repo's `.gitleaksignore` suppresses, so they're
seen again before the repo goes public.

**A real secret is never an exception.** Rotate it, and report it as
[`SECURITY.md`](../../SECURITY.md) says. It's in the branch's history, so a commit that removes
it doesn't make it safe.
