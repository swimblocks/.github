# Reconciler workflows

Living reference for the two workflows that keep every SwimBlocks repo aligned with
[`.github/settings.yml`](../.github/settings.yml):
[`release.yml`](../.github/workflows/release.yml) and
[`rollout.yml`](../.github/workflows/rollout.yml). Keep this doc current as they change; the
decision history lives in [`docs/design/`](design/), most recently
[`0003`](design/0003-settings-releases-and-rollout.md).

## What they do

**`release.yml`** publishes a release tagged `settings-YYYY-MM-DD` every Monday at 06:00 UTC,
whether or not `settings.yml` changed. The tag pins the version the org is on, and publishing it
is what starts the rollout. The weekly cadence is also what keeps this repo's scheduled workflows
alive — GitHub disables them after 60 days without repository activity, and a published release
is activity where a workflow run is not. See
[`0003`](design/0003-settings-releases-and-rollout.md) for why that distinction sank the previous
design.

**`rollout.yml`** checks out a released tag and runs
[`scripts/apply-settings.py`](../scripts/apply-settings.py) against every repo in the org. The
script reads `settings.yml` and PATCHes any drift in merge methods, labels, branch protection,
and rulesets. Because it re-asserts every setting, it is also the drift check: anything changed
through the GitHub UI is put back. It triggers:

- **On any release** — `release: published`, whether cut weekly by `release.yml` or by hand.
- **On demand** — `workflow_dispatch` from the Actions tab, with an optional `tag` input
  (defaults to the latest release). This is how you re-run a rollout without cutting a release.
- **On repo creation** — a `repo-created` `repository_dispatch` event.

It carries no `schedule` trigger, so GitHub's inactivity disabling cannot reach it.

Each rollout writes a job summary table of repo → result → version, and stamps the tag onto every repo
that came through clean as the `settings_version` custom property — a repo with drift left on it is
deliberately not stamped, which is what keeps it in the drift query's output. The summary says what one run did; the property
says what state a repo is in — see [The `settings_version` property](#the-settings_version-property)
for the query that reads it.

## Authentication

Both workflows authenticate as **GitHub Apps**, not personal tokens. At the start of each run,
`actions/create-github-app-token@v1` mints a short-lived (~1 hour) installation token. Nothing to
rotate on a schedule.

There are two apps, because they need different permissions on different scopes — and neither
grant belongs on the other's installation:

| App | Used by | Installed on | Permissions | Secrets |
|---|---|---|---|---|
| `swimblocks-reconciler` | `rollout.yml` | **All repositories** in the org | Metadata read; Administration read & write; Issues read & write; Custom properties read & write | `APP_ID`, `APP_PRIVATE_KEY` |
| `swimblocks-releaser` | `release.yml` | **`swimblocks/.github` only** | Metadata read; Contents read & write | `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY` |

The reconciler's permissions are what the script's API calls require, one to one:

| Permission | Grants | Used for |
|---|---|---|
| Metadata read | `GET /repos/{repo}` | `gh repo list`, and reading back what was applied |
| Administration read & write | `PATCH /repos/{repo}`, branch protection, rulesets | merge methods, protection, rulesets |
| Issues read & write | `POST /repos/{repo}/labels` | creating any label `settings.yml` lists and the repo lacks |
| Custom properties read & write | `PATCH /repos/{repo}/properties/values` | recording `settings_version` |

That last one is the whole of what the repository-level Custom properties permission grants — one
endpoint, no read of anything else. The org-level equivalent, `PATCH /orgs/{org}/properties/values`,
would set every repo in one call but rides on the *organization* Custom properties permission,
which also carries create, update and delete of every property definition in the org. Per-repo
calls are the cheaper price.

Neither app has a webhook configured.

**Why the release is not cut with `GITHUB_TOKEN`.** An event raised by `GITHUB_TOKEN` starts no
further workflow run, so a release published with it would never reach `rollout.yml`. An App
installation token raises real events, so `release: published` fires normally.

**Why a second app rather than Contents write on the reconciler.** The reconciler is installed on
every repo in the org, so adding Contents write there would hand org-wide push access to a
credential that only needs to change settings. The releaser is installed on `.github` alone,
where `main` is already gated by CODEOWNERS review.

All four secrets live on `swimblocks/.github` under Settings → Secrets and variables → Actions.

**`APP_ID` / `RELEASE_APP_ID` hold the app's Client ID** (`Iv23li…`), not the numeric App ID.
GitHub recommends the Client ID for minting installation tokens and shows it beside the App ID on
the app's settings page; `create-github-app-token` accepts either in its `app-id` input, so the
secret names are unchanged and an existing numeric value keeps working.

> The last step of each runbook below dispatches a workflow. GitHub only offers
> `workflow_dispatch` for workflows already on `main`, so neither verification can run from a
> branch — merge first, then dispatch.

## Setup / recreate `swimblocks-reconciler`

Perform once (or when recreating the app from scratch). Requires org-owner access.

1. **github.com → `swimblocks` org Settings → Developer settings → GitHub Apps → New GitHub App.**
2. Fill in:
   - **Name:** `swimblocks-reconciler`
   - **Homepage URL:** `https://github.com/swimblocks`
   - **Webhooks:** uncheck *Active*
   - **Repository permissions → Metadata:** Read (auto-selected)
   - **Repository permissions → Administration:** Read & write
   - **Repository permissions → Issues:** Read & write
   - **Repository permissions → Custom properties:** Read & write
   - All other permissions: No access
3. **Create GitHub App.** Note the **Client ID** on the next page (the numeric **App ID** beside
   it also works — see Authentication above).
4. **Private keys → Generate a private key.** A `.pem` file downloads.
5. **Install App → `swimblocks` → All repositories.**
6. On `swimblocks/.github`: **Settings → Secrets and variables → Actions → New repository secret**:
   - `APP_ID` = the Client ID from step 3
   - `APP_PRIVATE_KEY` = full contents of the `.pem` from step 4
7. Delete the local `.pem` file once stored as the secret.
8. Define the `settings_version` property — see
   [The `settings_version` property](#the-settings_version-property). The rollout fails on every
   repo until it exists.
9. Check it works. `rollout.yml` is the workflow that uses this app, so run it:

   ```bash
   gh workflow run rollout.yml -R swimblocks/.github
   gh run list -R swimblocks/.github --workflow rollout.yml --limit 1
   ```

   **Looking for:** that run goes green, with the `create-github-app-token` and
   `Apply settings to every repo in swimblocks` steps both passing (`gh run view <id>`, or the
   Actions tab). If the first step fails, the secrets are wrong or the app isn't installed — see
   Troubleshooting.

## Setup / recreate `swimblocks-releaser`

Same shape, narrower scope. `release.yml` fails at its first step until this exists.

1. **github.com → `swimblocks` org Settings → Developer settings → GitHub Apps → New GitHub App.**
2. Fill in:
   - **Name:** `swimblocks-releaser`
   - **Homepage URL:** `https://github.com/swimblocks`
   - **Webhooks:** uncheck *Active*
   - **Repository permissions → Metadata:** Read (auto-selected)
   - **Repository permissions → Contents:** Read & write
   - All other permissions: No access
3. **Create GitHub App.** Note the **Client ID** (`Iv23li…`) on the next page.
4. **Private keys → Generate a private key.** A `.pem` file downloads.
5. **Install App → `swimblocks` → Only select repositories → `.github`.** Not all repositories —
   the narrow install is the whole point of a second app.
6. On `swimblocks/.github`, add the repository secrets:
   - `RELEASE_APP_ID` = the Client ID from step 3
   - `RELEASE_APP_PRIVATE_KEY` = full contents of the `.pem` from step 4
7. Delete the local `.pem` file once stored as the secret.
8. Check it works. `release.yml` is the workflow that uses this app, so run it:

   ```bash
   gh workflow run release.yml -R swimblocks/.github
   ```

   **Looking for two things**, roughly a minute apart:

   ```bash
   gh release list -R swimblocks/.github --limit 1          # a settings-YYYY-MM-DD release
   gh run list -R swimblocks/.github --workflow rollout.yml --limit 1
   ```

   The release must be there **and** a `rollout.yml` run must have started behind it. A release
   with no rollout behind it means the release was not published with the App token — that is
   the whole reason this app exists.

> **Adding a permission to an app already installed.** Editing an app's permissions does not
> change what its tokens can do. GitHub raises an installation request that an org owner has to
> accept (org Settings → GitHub Apps → *Configure* on the app → **Review request**), and until
> then the app keeps its old permissions. That is the usual reason a freshly granted permission
> still 403s.

## The `settings_version` property

Every rollout records the release it applied on each repo as a repository custom property, so
"which repos are behind" is one query rather than a trawl through run logs. This is what
`officials-admin` needed and nobody had: it sat unreconciled from creation until someone noticed
by hand ([#34](https://github.com/swimblocks/.github/issues/34)).

**Define it once**, as an org owner. It is deliberately not something the reconciler can do — the
app holds values write, not schema admin:

```bash
gh api -X PUT orgs/swimblocks/properties/schema/settings_version \
  -f value_type=string \
  -f description='Version of org-wide settings last synced from swimblocks/.github' \
  -F required=false \
  -f values_editable_by=org_and_repo_actors
```

`required=false` and **no default value**: a default is reported for every repo whether or not it
was ever reconciled, which would turn the query below into a false all-clear.

`values_editable_by` is the one that decides whether the rollout works at all, and it defaults to
`org_actors` — org owners and property managers only. The reconciler holds the *repository*
Custom properties permission and writes through the *repository* endpoint, so it acts as a repo
actor and that default shuts it out. `org_and_repo_actors` also lets a repo admin set the value by
hand, which is the cost: the property is a claim the rollout makes, and a hand-set value is a claim
nothing verified. Check it with:

```bash
gh api orgs/swimblocks/properties/schema/settings_version --jq .values_editable_by
```

**Which repos are behind:**

```bash
export WANT=$(gh release view -R swimblocks/.github --json tagName --jq .tagName)
gh api orgs/swimblocks/properties/values --paginate \
  --jq '.[] | select(([.properties[]
        | select(.property_name == "settings_version") | .value] | first) != env.WANT)
        | .repository_full_name'
```

Empty output means every repo is on the current release. Anything listed is either behind or has
never been reconciled — the query does not distinguish, and does not need to: both call for a
rollout. (`gh`'s `--jq` is gojq, hence `env.WANT` rather than `jq --arg`; no separate `jq` binary
is needed.)

**What one repo says:**

```bash
gh api repos/swimblocks/officials-admin/properties/values
```

## Rotate a private key

If the key is compromised or expiring:

1. App settings → **Private keys → Generate a private key** (you can have two active at once).
2. Replace the matching secret on `swimblocks/.github` with the new `.pem` contents —
   `APP_PRIVATE_KEY` for the reconciler, `RELEASE_APP_PRIVATE_KEY` for the releaser.
3. Run the workflow that uses it (`rollout.yml` or `release.yml`) to confirm it still
   authenticates.
4. Delete the old key from the app's settings page.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `rollout.yml` fails at `create-github-app-token` | `APP_ID` / `APP_PRIVATE_KEY` secret missing or malformed, or `swimblocks-reconciler` isn't installed on the org. |
| `No repos found` | App lacks Metadata read, or isn't installed on the repos. |
| `SKIP branches.<branch>` on a private repo | Expected: GitHub Free disallows branch protection on private repos. Promote the repo to public to enable it. |
| A release published but no rollout ran | The release was cut with `GITHUB_TOKEN` rather than the `swimblocks-releaser` App, so it raised no event; or `rollout.yml` is missing from the default branch. Re-run `rollout.yml` from the Actions tab with the release tag as the `tag` input. |
| `release.yml` fails at `create-github-app-token` | `RELEASE_APP_ID` / `RELEASE_APP_PRIVATE_KEY` missing or malformed, or `swimblocks-releaser` isn't installed on `.github`. |
| `release.yml` says the tag is already published | Expected on a same-day re-run. Roll the existing release out with `rollout.yml`'s `workflow_dispatch` instead. |
| `release.yml` state is `disabled_inactivity` | Re-enable with `gh workflow enable release.yml -R swimblocks/.github`. Activity alone never re-enables a workflow. |
| Ruleset apply fails on a public repo | App lacks Administration write, or the ruleset payload in `settings.yml` is malformed. |
| `FAIL settings_version` with `(HTTP 422)` on every repo | The property isn't defined on the org yet — see [The `settings_version` property](#the-settings_version-property). |
| `FAIL settings_version` with `(HTTP 403)` | One of three: `swimblocks-reconciler` lacks Custom properties write; the permission was added but the installation request hasn't been accepted; or the property's `values_editable_by` is `org_actors`, which locks out the repository endpoint the app writes through. |
| The drift query lists a repo the rollout reported OK | The rollout ran before the property existed, or from a tag predating it. Re-run `rollout.yml`. |
