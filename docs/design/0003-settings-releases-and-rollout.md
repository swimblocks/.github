# 0003 — Settings as a versioned release, rolled out weekly

Status: implemented

## Context

`reconcile-repo-defaults.yml` applied `.github/settings.yml` across the org weekly, on
`workflow_dispatch`, and on a `repo-created` `repository_dispatch`. On 2026-08-03 it stopped
running, and stayed stopped:

```
gh api repos/swimblocks/.github/actions/workflows/285906161 -q .state
disabled_inactivity
```

GitHub disables scheduled workflows in **public** repos after 60 days without repository
activity. `.github` went from 2026-06-03 to 2026-08-07 without a commit, and the workflow was
switched off inside that gap.

Three properties of the disabling matter here.

**Workflow runs are not repository activity.** The reconciler ran successfully every Monday
from Jun 8 to Aug 3 — nine runs inside the quiet window — and was disabled anyway. A scheduled
workflow cannot keep itself alive by running; only a repository *event* resets the clock.

**A reconciler can never generate that event.** Its entire effect is on other repositories.
Contrast `swim-club-tech-survey`, whose monthly crawl publishes a release to its own repo:
96 days since its last human commit and its schedule is still active.

**Disabling is per-workflow and kills every trigger, not just the cron.** The 422 recorded on
[#34](https://github.com/swimblocks/.github/issues/34) —
`Cannot trigger a 'workflow_dispatch' on a disabled workflow` — means the `repo-created` path
was dead too, so a repo created outside `create-repo.sh` got nothing. That is exactly what
happened to `officials-admin`. And activity does not undo it: `#47` and `#48` merged while the
workflow stayed `disabled_inactivity`. Someone has to re-enable it by hand.

The cost was concrete. `#48` merged label reconciliation, and the `no-issue` label existed in no
repo until the workflow was re-enabled manually.

## Design

Two workflows replace the one, split so that neither the cadence nor the effect can go dormant.

### `release.yml` — the cadence

`on: schedule` (Mondays 06:00 UTC) + `workflow_dispatch`. Publishes a release tagged by date:

```
settings-2026-09-08
```

matching the convention `swim-club-tech-survey` already uses (`survey-2026-09-01-1117`). Notes
come from `--generate-notes`, which is the commit range since the previous tag. It publishes
weekly whether or not `settings.yml` changed: the fixed cadence is what guarantees the activity,
and an unchanged release still states which version the org is on.

This workflow is schedule-triggered and so is disable-eligible — but it is self-sustaining for
the same reason the survey is. Publishing a release is an event in this repo, every week,
comfortably inside the 60-day window.

### `rollout.yml` — the effect

`on: release: [published]` + `workflow_dispatch` + `repository_dispatch: [repo-created]`. It
checks out the released tag and runs `apply-settings.py` across every repo in the org. It carries
no `schedule`, so it is not disable-eligible at all: the path that actually changes repos cannot
go dormant.

One rollout does both old jobs. It applies whatever the release contains, and because it
re-asserts every setting it corrects drift introduced through the GitHub UI — the role the weekly
cron used to serve. The `repo-created` hook moves here unchanged, so a repo created outside
`create-repo.sh` is reconciled immediately rather than by the next release.

### The handoff between them

An event raised by `GITHUB_TOKEN` does not start another workflow run. A release cut with the
workflow's own token would therefore reach nothing, and `rollout.yml` would sit idle while
releases piled up. An App installation token raises real events, so the release is cut with one
and `release: published` is the only trigger the automated path needs.

That token comes from a **second App, `swimblocks-releaser`**: Metadata read plus Contents write,
installed on `swimblocks/.github` alone. The obvious shortcut — reusing `swimblocks-reconciler` —
was rejected. That App is installed on *all repositories* in the org, so adding Contents write to
it would hand org-wide push access to a credential that only needs to change settings. Two apps
cost a second private key to store and rotate; that is the price of keeping each grant as narrow
as the job it does.

The alternative considered and dropped was for `release.yml` to dispatch the rollout explicitly
(`gh workflow run rollout.yml --raw-field tag=…`) under `GITHUB_TOKEN`. It works with no setup at
all, but leaves `rollout.yml` carrying two trigger paths where only one ever fires automatically,
and it needs `actions: write` on the workflow token.

### Release contents

The release is a tag and generated notes, with no attached asset. The tag already addresses the
exact file — `git show <tag>:.github/settings.yml`, or the contents API with `?ref=<tag>` — and
`rollout.yml` reads it by checking the tag out. An asset would earn its place only if something
outside git needed `settings.yml` by URL, which nothing does.

(Contrast `swim-club-tech-survey`, which attaches its results CSV: there the file is the product
people come to the release page to download.)

### Version traceability

Nothing on a repo records which settings version it is on, which is why `officials-admin` could
sit unreconciled without anyone noticing. `apply-settings.py` gains `--version` and
`--summary-file`, and the rollout points the latter at `$GITHUB_STEP_SUMMARY`, so every run
leaves a table of repo → result → version. The release page plus the run history become the audit
trail.

That answers "what did this run do". It does not answer "which repos are behind", which needs
state on the repo rather than in a run log. So the rollout also stamps the tag onto each repo as
the `settings_version` repository custom property, and
`GET /orgs/swimblocks/properties/values` answers the question in one call
([#53](https://github.com/swimblocks/.github/issues/53); the query is in
[`docs/reconciler.md`](../reconciler.md#the-settings_version-property)).

The write goes per repo, through `PATCH /repos/{owner}/{repo}/properties/values`. That endpoint is
the entirety of what the repository-level Custom properties permission grants, so the reconciler
gains one narrow capability and nothing else. The org-level `PATCH /orgs/{org}/properties/values`
would do all seven repos in a single call, but it rides on the *organization* Custom properties
permission, which also carries create, update and delete of every property definition in the org —
the same test that put the releaser in its own app rather than widening the reconciler.

Defining `settings_version` stays an org-owner action, outside what either app can do. Until it
exists the write 422s and the rollout goes red on every repo; that is the intended signal, since
neither a missing definition nor a missing permission is a state to sit in. The property carries no
default value, because a default would be reported for repos that were never reconciled and read
as an all-clear.

## Verification

- `release.yml` run publishes `settings-YYYY-MM-DD` and a `rollout.yml` run appears behind it.
  A release with no rollout behind it means the release was cut with `GITHUB_TOKEN`, not the App.
- The rollout's job summary lists every repo in the org against the released tag, and the drift
  query in [`docs/reconciler.md`](../reconciler.md#the-settings_version-property) returns nothing
  afterwards.
- `gh api repos/swimblocks/.github/actions/workflows/<release id> -q .state` stays `active`
  across a quiet stretch longer than 60 days.
- A `repo-created` `repository_dispatch` starts a rollout.
- `ruff check .` and `pytest -q` pass; `summary_table` and `parse_args` are covered in
  `tests/test_apply_settings.py`.

### Prerequisite

`release.yml` fails at its first step until `swimblocks-releaser` exists and
`RELEASE_APP_ID` / `RELEASE_APP_PRIVATE_KEY` are set on `swimblocks/.github`. `rollout.yml` fails
on every repo until `settings_version` is defined on the org and `swimblocks-reconciler` holds
Custom properties write. Both runbooks are in [`docs/reconciler.md`](../reconciler.md).

## Open items

- **Failure policy on rollout.** `apply-settings.py` accumulates failures and exits non-zero at
  the end rather than stopping at the first bad repo. That is deliberate for a rollout across
  many repos — one repo's 403 must not strand the rest — and is recorded here as the intended
  behaviour rather than an accident.
