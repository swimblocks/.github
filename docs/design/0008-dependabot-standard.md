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

### Where the rules live

The rules are split across two guides, the way the style guide and the security guide already
split:

- **The [security guide](../security/README.md) sets the expectation,** as a new rule,
  `security/dependencies`. Every repo is told about known vulnerabilities in what it depends on
  and has their fixes proposed. Every repo also waits before taking a newly published version,
  so a compromised release has time to be found and pulled. The rule says what's expected, and
  points to the dependency guide for how.
- **A new dependency guide, `docs/dependencies/README.md`, says how we meet it.** It covers
  Dependabot's configuration, the cooldown's length, and package managers' own age gates. Its
  rules have IDs `dependencies/<heading>`, as the security guide's do. Later rules about
  dependencies go there too, licences first, in designs of their own.

The style and security guides each have a review that checks pull requests against them. The
dependency guide will get one too, but not in this design. Until then, `settings.yml` and the
reconciler enforce it.

The rest of this section is what each guide gains.

### What every repo's `dependabot.yml` covers

This section is the dependency guide's `dependencies/dependabot`.

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
- **One group for minor and patch updates.** Each week, an ecosystem's minor and patch updates
  arrive together as one pull request, and each major update as its own. Minor and patch
  updates are most of the volume, so grouping them means one CI run and one review per
  ecosystem each week, not one per dependency. Majors are where breaking changes are, so each
  stays alone and a person merges it.

  A failing grouped pull request doesn't name the update that broke it, so a person finds it in
  the CI log. `@dependabot ignore <dependency>` then takes that update out of the group until
  it's fixed.

  The group applies only to version updates, because a group without `applies-to:
  security-updates` doesn't touch security updates. So each security fix still arrives alone and
  immediately.

```yaml
- package-ecosystem: uv
  directory: /
  schedule:
    interval: weekly
  cooldown:
    default-days: 7
  groups:
    minor-and-patch:
      update-types: [minor, patch]
```

`open-pull-requests-limit` stays at Dependabot's default of five. Security updates have their
own fixed limit of ten, and aren't affected.

A repo adds what it needs beyond that: more directories, `ignore` rules, labels. A directory a
repo doesn't want version updates for, such as a prototype, keeps an entry with
`open-pull-requests-limit: 0`, which turns off its version updates but keeps its security
updates. The exception is then in the repo's own file, reviewed like any change.

### Cooldown

This section is the dependency guide's `dependencies/cooldown`.

**We wait 7 days.** Every entry sets `cooldown: default-days: 7`, so Dependabot proposes a
version only once it has been published for a week. That holds in every ecosystem, and for patch,
minor and major updates alike. A repo may wait longer, never shorter.

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

Dependabot's cooldown covers only Dependabot's pull requests. A person or agent running
`uv add` or `uv lock --upgrade` still gets whatever was published a minute ago. So we expect
the package manager's own age gate to wait the same 7 days: every uv project sets
`exclude-newer = "7 days"` under `[tool.uv]` in its `pyproject.toml`. A repo that sets a
different value says why in a comment on the line above it. The value may be shorter than
Dependabot's cooldown, but never longer, because Dependabot would then propose versions uv won't
install, and its lockfile updates would fail. The reconciler's check (below) fails a repo that
breaks either rule. Whether uv's age gate also blocks security updates is still open (see
Open items).

### The reconciler checks it

The reconciler (`rollout.yml`, running `apply_settings.py`) reads each repo's `dependabot.yml`
and the file list of its default branch, and fails the repo if:

- it has no `dependabot.yml`;
- an ecosystem and directory from the table above has no entry covering it (`directory`, or a
  matching `directories` glob);
- an entry isn't weekly, or any of its cooldown days (`default-days`, or a `semver-*-days`
  that overrides it) is shorter than the org's;
- an entry has no group that takes its minor and patch updates;
- a uv project has no `exclude-newer`, sets one longer than the org's cooldown, or sets a value
  other than the cooldown with no comment on the line above saying why.

The reconciler fixes settings in place: merge methods, rulesets, labels, and the alerts below.
It doesn't fix files. It reports a failing repo's `dependabot.yml` or `pyproject.toml`, as it
reports a missing review caller, and a pull request fixes the repo. Fixing files itself would
take Contents write on every repo, where today the reconciler's app has only Contents read
([`docs/reconciler.md`](../reconciler.md)). On GitHub Free, private repos have no ruleset, so
that grant would let a leaked app key push straight to their `main`.

`settings.yml` holds the org's values (the interval and the cooldown), so changing them is one
change in one place, and the check follows.

### Alerts and security updates

Dependabot alerts and Dependabot security updates are what meet the first half of
`security/dependencies`. They're free on every repo, private ones included. They're repo
settings, not `dependabot.yml` keys, and security updates need alerts on. Every repo turns both
on, and the rule is kept the way `security/secrets` is:

| | How |
|---|---|
| The security guide states it | A `Dependencies` section: every repo is told about known vulnerabilities and has their fixes proposed, and waits before taking a new release. It links the dependency guide for how |
| The dependency guide implements it | `dependencies/dependabot` and `dependencies/cooldown`, above, and a section on the two settings |
| The reconciler fixes it | `settings.yml` turns both on in every repo (`PUT /repos/{repo}/vulnerability-alerts`, `PUT /repos/{repo}/automated-security-fixes`). Each rollout turns them back on and reads them back |
| The security review checks it | A new job, `security / dependencies`, fails a pull request in a repo whose alerts are off. It asks the alerts API (`GET /repos/{repo}/dependabot/alerts`), which answers 403 when they're off. That takes the workflow permission `vulnerability-alerts: read`, which the caller has to grant |

The review can't see whether security updates are on, because reading that setting takes admin
read and a workflow's token can't have it. The reconciler's read-back is the only check there.

The permission has to be granted before the job asks for it. A reusable workflow gets no more
than its caller grants, and a job that asks for more fails the whole run, `security / secrets`
included. So every repo's caller grants it first (rollout step 2), and the job lands after.

### New repos

`scripts/create-repo.sh` commits a starting `dependabot.yml` with the `github-actions` entry,
which every repo needs once it has the review callers. When the repo gains a `pyproject.toml`
or a `go.mod`, the reconciler's check asks for that ecosystem's entry.

### Auto-merge, after #43

Once CI is required, each ecosystem's weekly minor-and-patch pull request merges itself when
green; majors are always merged by a person. Two things stand in the way besides #43, and are
decided then:

- **The required code-owner review.** The ruleset requires an approval from a code owner, which
  Dependabot can't give and `github-actions[bot]` isn't. Either a person approves and auto-merge
  then waits for CI, or something that counts as a code owner approves for them, which is the
  gate approving itself.
- **Where the workflow lives.** It needs a caller in every repo, or a job in one the repos
  already have.

`allow_auto_merge` is a repo setting `apply_settings.py` already applies; `settings.yml` turns it
on then.

## Rollout

1. `settings.yml` turns on alerts and security updates in every repo. The security guide gains
   `security/dependencies`, and the dependency guide is written. No repo changes.
2. The security review's caller template grants `vulnerability-alerts: read`. A pull request in
   each repo copies the new caller, brings its `dependabot.yml` up to the standard with the
   cooldown, and sets `exclude-newer` in a uv project. Agent-opened and merged, as a mechanical
   change across repos.
3. The security review gains `security / dependencies`, once every repo's caller grants the
   permission.
4. The reconciler's `dependabot.yml` check lands once every repo passes it, so it doesn't fail
   the org on the day it ships.
5. `create-repo.sh` commits the starting file. `CONTRIBUTING.md` → Dependencies and
   `AGENTS.md` link the dependency guide. `docs/reconciler.md` describes the reconciler's check,
   and `docs/security-review.md` the new job.
6. Auto-merge, under #16, once #43 is done.

## Verification

- The reconciler's check passes on every repo after step 2, and fails a test repo with an
  ecosystem left out.
- Alerts and security updates read back as enabled on all twelve repos after a rollout.
- `security / dependencies` passes on a pull request in a repo with alerts on, and fails one in
  a test repo with them off.
- A week after step 2, Dependabot has opened pull requests only for versions older than the
  cooldown.

## Open items

- **Ecosystems not in the table** (`docker-compose`, `pre-commit`, Helm) join it when a repo
  first uses one.
- **uv's age gate and security updates.** Dependabot's cooldown never delays a security update,
  but uv applies `exclude-newer` to every lock, Dependabot's included. A security fix published
  less than 7 days ago may then fail to lock, and its security update with it. Dependabot turns
  pnpm's and Yarn Berry's age gates off on security updates; nothing says it does for uv's. A
  test repo settles it before step 2 sets `exclude-newer` anywhere. If the lock fails, the
  dependency guide either names `exclude-newer-package` as the way to let one fix through, or
  makes the age gate a recommendation rather than something the reconciler checks.
- **Age gates beyond uv,** such as npm's or pnpm's, join the check when a repo's package manager
  has one. Go modules have none.
- **A dependency review,** checking each pull request against the dependency guide as the
  readability and security reviews check theirs. It would catch a pull request that adds a
  `go.mod` without a `gomod` entry when it's opened, rather than at the next rollout.
- **Vulnerability scanning on pull requests**
  ([#98](https://github.com/swimblocks/.github/issues/98)). Dependabot alerts see a known
  vulnerability only once it's on the default branch. Checking each pull request against
  [OSV](https://osv.dev/) would stop one from being merged at all.
- **Licences** ([#99](https://github.com/swimblocks/.github/issues/99)), the dependency guide's
  next rule, in a design of its own. GitHub's
  [dependency review action](https://github.com/actions/dependency-review-action) can fail a
  pull request on a disallowed licence.
