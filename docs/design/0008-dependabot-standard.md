# 0008 — A Dependabot standard for every repo

Status: proposed

Tracking issue: [#16](https://github.com/swimblocks/.github/issues/16).

## Context

GitHub has no org-wide Dependabot configuration: each repo's `.github/dependabot.yml` decides
what Dependabot updates, and two repo settings decide whether it raises alerts and security
fixes at all. Nothing checks either, and they have drifted:

| | Repos |
|---|---|
| No `dependabot.yml` | deck-eval-parser, swim-club-tech-survey, officials-admin, `.github-private`, tinyurl-plugin, rems-sync-apps-script |
| A `dependabot.yml` that misses an ecosystem the repo uses | `.github` (no `pip`), rems-sync (no `terraform`) |
| Complete | deck-eval-gen, semotion-sync, swim-meet-almanac, fetch-service |
| Dependabot alerts on | `.github`, deck-eval-gen; off in the other ten |
| Dependabot security updates on | none |

The repos also differ in what they need updated: `uv` or `pip` for Python, `gomod`, `npm`,
`docker`, `terraform`, `devcontainers`, and `github-actions` in every repo. So one file copied
unchanged into every repo, as the review callers are (`required_files`), can't be the standard.

Updates arrive one pull request each, and today someone merges each by hand; 24 are open across
the org. Auto-merging them is wanted, but waits on CI being a required check
([#43](https://github.com/swimblocks/.github/issues/43)): auto-merge waits only on required
checks, so without it untested updates would merge.

## Design

### What every repo's `dependabot.yml` covers

An entry for every ecosystem the repo uses, found from the files in its tree:

| File | Ecosystem | Directory |
|---|---|---|
| `.github/workflows/*.yml` | `github-actions` | `/` (every repo) |
| `uv.lock` | `uv` | its directory |
| `requirements*.txt` or `pyproject.toml`, with no `uv.lock` beside it | `pip` | its directory |
| `go.mod` | `gomod` | its directory |
| `package.json` | `npm` | its directory |
| `Dockerfile` | `docker` | its directory |
| `*.tf` | `terraform` | its directory |
| `.devcontainer/devcontainer.json` | `devcontainers` | `/` |

Each entry has:

- **`schedule.interval: weekly`**, Dependabot's default day, Monday.
- **The org's cooldown, or a longer one** (below).
- **No `groups:`.** Each update is its own pull request. A failing update then names itself,
  and can be reverted on its own. Grouping would mainly save clicks, which auto-merge saves
  instead, and Dependabot closes a pull request a newer version supersedes.

`open-pull-requests-limit` stays at Dependabot's default of five. Security updates have their
own fixed limit of ten, and aren't affected.

A repo adds what it needs beyond that: more directories, `ignore` rules, labels. A directory a
repo doesn't want version updates for, such as a prototype, keeps an entry with
`open-pull-requests-limit: 0`, which turns off its version updates but keeps its security
updates. The exception is then in the repo's own file, reviewed like any change.

### Cooldown

Every entry waits **7 days** after a version is published before proposing it
(`cooldown: default-days: 7`), whatever the ecosystem and whether the update is a patch, minor
or major. A repo may set longer, not shorter.

Cooldown is the defence against a compromised release: a malicious version is usually found
and pulled within hours (chalk and debug in September 2025 in about two; litellm on PyPI in
about two and a half; PyPI handled 92% of 2025's reports within a day), but some lasted days
(about fifteen Shai-Hulud 2.0 versions were still on npm three days in). Seven days is what
security tooling recommends ([zizmor](https://docs.zizmor.sh/audits/),
[Datadog](https://securitylabs.datadoghq.com/articles/dependency-cooldowns/),
[Woodruff](https://blog.yossarian.net/2025/11/21/We-should-all-be-using-dependency-cooldowns)),
where Dependabot's own default, since
[July 2026](https://github.blog/changelog/2026-07-14-dependabot-version-updates-introduce-default-package-cooldown/),
and Renovate's presets are three, matching npm's 72-hour unpublish window. The margin past three
matters most once patch and minor updates merge themselves.

Patches get no shorter wait: compromised releases are usually patch bumps (chalk 5.6.1, debug
4.4.2, ultralytics 8.3.41), and no source recommends different days by bump size. Security
updates are never delayed by cooldown, so its cost is only how current ordinary updates are.

A cooldown can't help where the thing referenced can change under it: a GitHub Action used by
tag, whose tag can be moved (tj-actions in March 2025), or a Go module proxy serving a cached
malicious version. Pinning actions to a commit, as the readability review does, is the defence
there, and belongs in the [security guide](../security/README.md) rather than this standard.

A repo that also sets a package manager's own age gate, such as uv's `exclude-newer`, keeps
Dependabot's cooldown at least as long, or Dependabot's lockfile updates fail.

### The rollout checks it

The rollout reads each repo's `dependabot.yml` and the file list of its default branch, and fails
the repo if:

- it has no `dependabot.yml`;
- an ecosystem and directory from the table above has no entry covering it (`directory`, or a
  matching `directories` glob);
- an entry isn't weekly, or its cooldown is shorter than the org's.

It never writes the file: the reconciler has Contents read, not write
([`docs/reconciler.md`](../reconciler.md)). A failing repo is fixed by a pull request, as a
missing review caller is. `settings.yml` holds the org's values (the interval and the
cooldown), so changing them is one change in one place, and the check follows.

### Alerts and security updates in `settings.yml`

Dependabot alerts (`PUT /repos/{repo}/vulnerability-alerts`) and Dependabot security updates
(`PUT /repos/{repo}/automated-security-fixes`) are free on every repo, private ones included,
and are settings rather than `dependabot.yml` keys. Security updates need alerts on. `settings.yml` turns both on in
every repo, and the rollout turns them back on if they're turned off.

### New repos

`scripts/create-repo.sh` commits a starting `dependabot.yml` with the `github-actions` entry,
which every repo needs once it has the review callers. When the repo gains a `pyproject.toml`
or a `go.mod`, the check asks for that ecosystem's entry.

### Auto-merge, after #43

Once CI is required, Dependabot's patch and minor updates merge themselves when green; majors
are always merged by a person. Two things stand in the way besides #43, and are decided then:

- **The required code-owner review.** The ruleset requires an approval from a code owner, which
  Dependabot can't give and `github-actions[bot]` isn't. Either a person approves and auto-merge
  then waits for CI, or something that counts as a code owner approves for them, which is the
  gate approving itself.
- **Where the workflow lives.** It needs a caller in every repo, or a job in one the repos
  already have.

`allow_auto_merge` is a repo setting `apply_settings.py` already applies; `settings.yml` turns it
on then.

## Rollout

1. `settings.yml` turns on alerts and security updates in every repo. No repo changes.
2. A pull request in each repo whose `dependabot.yml` is missing or incomplete brings it up to
   the standard, with the cooldown. Agent-opened and merged, as a mechanical change across
   repos.
3. The rollout's check lands once every repo passes it, so it doesn't fail the org on the day
   it ships.
4. `create-repo.sh` commits the starting file. `CONTRIBUTING.md` → Dependencies states the
   standard, and `docs/reconciler.md` the check.
5. Auto-merge, under #16, once #43 is done.

## Verification

- The check passes on every repo after step 2, and fails a test repo with an ecosystem left out.
- Alerts and security updates read back as enabled on all twelve repos after a rollout.
- A week after step 2, Dependabot has opened pull requests only for versions older than the
  cooldown.

## Open items

- **Groups,** if pull request volume or CI time becomes the problem. Not while auto-merge can
  take the clicks.
- **Ecosystems not in the table** (`docker-compose`, `pre-commit`, Helm) join it when a repo
  first uses one.
