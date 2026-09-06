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

Each rollout writes a job summary table of repo → result → version. That plus the release page is
the record of which repos are on which settings version.

## Authentication

Both workflows authenticate as **GitHub Apps**, not personal tokens. At the start of each run,
`actions/create-github-app-token@v1` mints a short-lived (~1 hour) installation token. Nothing to
rotate on a schedule.

There are two apps, because they need different permissions on different scopes — and neither
grant belongs on the other's installation:

| App | Used by | Installed on | Permissions | Secrets |
|---|---|---|---|---|
| `swimblocks-reconciler` | `rollout.yml` | **All repositories** in the org | Metadata read; Administration read & write | `APP_ID`, `APP_PRIVATE_KEY` |
| `swimblocks-releaser` | `release.yml` | **`swimblocks/.github` only** | Metadata read; Contents read & write | `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY` |

The reconciler's permissions are what the script's API calls require: Metadata read for
`gh repo list` and `GET /repos/{repo}`, Administration write for `PATCH /repos/{repo}`, branch
protection and rulesets. Neither app has a webhook configured.

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
   - All other permissions: No access
3. **Create GitHub App.** Note the **Client ID** on the next page (the numeric **App ID** beside
   it also works — see Authentication above).
4. **Private keys → Generate a private key.** A `.pem` file downloads.
5. **Install App → `swimblocks` → All repositories.**
6. On `swimblocks/.github`: **Settings → Secrets and variables → Actions → New repository secret**:
   - `APP_ID` = the Client ID from step 3
   - `APP_PRIVATE_KEY` = full contents of the `.pem` from step 4
7. Delete the local `.pem` file once stored as the secret.
8. Trigger `rollout.yml` via `workflow_dispatch` — that is the workflow this app authenticates —
   and confirm the `create-github-app-token` and `Apply settings` steps both pass.

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
8. Trigger `release.yml` via `workflow_dispatch` and confirm it publishes a `settings-YYYY-MM-DD`
   release **and** that a `rollout.yml` run starts behind it. A release with no rollout behind it
   means the App token was not the one that published it.

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
