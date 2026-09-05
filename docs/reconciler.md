# Reconciler workflows

Living reference for the two workflows that keep every SwimBlocks repo aligned with
[`.github/settings.yml`](../.github/settings.yml):
[`release.yml`](../.github/workflows/release.yml) and
[`rollout.yml`](../.github/workflows/rollout.yml). Keep this doc current as they change; the
decision history lives in [`docs/design/`](design/), most recently
[`0003`](design/0003-settings-releases-and-rollout.md).

## What they do

**`release.yml`** publishes a release tagged `settings-YYYY-MM-DD` every Monday at 06:00 UTC,
whether or not `settings.yml` changed, then dispatches the rollout. The tag pins the version the
org is on. The weekly cadence is also what keeps this repo's scheduled workflows alive — GitHub
disables them after 60 days without repository activity, and a published release is activity
where a workflow run is not. See
[`0003`](design/0003-settings-releases-and-rollout.md) for why that distinction sank the previous
design.

**`rollout.yml`** checks out a released tag and runs
[`scripts/apply-settings.py`](../scripts/apply-settings.py) against every repo in the org. The
script reads `settings.yml` and PATCHes any drift in merge methods, labels, branch protection,
and rulesets. Because it re-asserts every setting, it is also the drift check: anything changed
through the GitHub UI is put back. It triggers:

- **From the weekly release** — `release.yml` dispatches it with the tag it just published.
- **On a release cut by hand** — `release: published`.
- **On demand** — `workflow_dispatch` from the Actions tab, with an optional `tag` input
  (defaults to the latest release).
- **On repo creation** — a `repo-created` `repository_dispatch` event.

It carries no `schedule` trigger, so GitHub's inactivity disabling cannot reach it.

Each rollout writes a job summary table of repo → result → version. That plus the release page is
the record of which repos are on which settings version.

## Authentication

`rollout.yml` authenticates as a **GitHub App** (`swimblocks-reconciler`), not a personal token.
At the start of each run, `actions/create-github-app-token@v1` mints a short-lived (~1 hour)
installation token scoped to the org. Nothing to rotate on a schedule.

Two repository secrets on `swimblocks/.github` drive it:

| Secret | Value |
|---|---|
| `APP_ID` | Numeric app ID from the app's settings page |
| `APP_PRIVATE_KEY` | Full contents of the app's `.pem` private key |

The app needs the minimum permissions the script's API calls require:

| Permission | Level | Used by |
|---|---|---|
| Repository → Metadata | Read | `gh repo list`, `GET /repos/{repo}` |
| Repository → Administration | Read & write | `PATCH /repos/{repo}`, branch protection, rulesets |

It is installed on **all repositories** in the org, with no webhook configured.

The release itself is cut with the workflow's own `GITHUB_TOKEN`, not the App — see
[`0003`](design/0003-settings-releases-and-rollout.md) for why the App is deliberately not
given Contents write.

## Setup / recreate the GitHub App

Perform once (or when recreating the app from scratch). Requires org-owner access.

1. **github.com → `swimblocks` org Settings → Developer settings → GitHub Apps → New GitHub App.**
2. Fill in:
   - **Name:** `swimblocks-reconciler`
   - **Homepage URL:** `https://github.com/swimblocks`
   - **Webhooks:** uncheck *Active*
   - **Repository permissions → Metadata:** Read (auto-selected)
   - **Repository permissions → Administration:** Read & write
   - All other permissions: No access
3. **Create GitHub App.** Note the **App ID** on the next page.
4. **Private keys → Generate a private key.** A `.pem` file downloads.
5. **Install App → `swimblocks` → All repositories.**
6. On `swimblocks/.github`: **Settings → Secrets and variables → Actions → New repository secret**:
   - `APP_ID` = the numeric App ID from step 3
   - `APP_PRIVATE_KEY` = full contents of the `.pem` from step 4
7. Delete the local `.pem` file once stored as the secret.
8. Trigger `rollout.yml` via `workflow_dispatch` and confirm the `create-github-app-token` and
   `Apply settings` steps both pass.

## Rotate the private key

If the key is compromised or expiring:

1. App settings → **Private keys → Generate a private key** (you can have two active at once).
2. Replace the `APP_PRIVATE_KEY` secret on `swimblocks/.github` with the new `.pem` contents.
3. Run `rollout.yml` to confirm it still authenticates.
4. Delete the old key from the app's settings page.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `create-github-app-token` step fails | `APP_ID` / `APP_PRIVATE_KEY` secret missing or malformed, or the app isn't installed on the org. |
| `No repos found` | App lacks Metadata read, or isn't installed on the repos. |
| `SKIP branches.<branch>` on a private repo | Expected: GitHub Free disallows branch protection on private repos. Promote the repo to public to enable it. |
| A release published but no rollout ran | The dispatch step in `release.yml` failed, or `rollout.yml` is missing from the default branch. Re-run it from the Actions tab with the release tag as the `tag` input. |
| `release.yml` state is `disabled_inactivity` | Re-enable with `gh workflow enable release.yml -R swimblocks/.github`. Activity alone never re-enables a workflow. |
| Ruleset apply fails on a public repo | App lacks Administration write, or the ruleset payload in `settings.yml` is malformed. |
