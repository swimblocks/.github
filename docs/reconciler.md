# Reconciler workflow

Living reference for [`reconcile-repo-defaults.yml`](../.github/workflows/reconcile-repo-defaults.yml)
— the scheduled workflow that keeps every SwimBlocks repo aligned with
[`.github/settings.yml`](../.github/settings.yml). Keep this doc current as the workflow changes;
the decision history lives in [`docs/design/`](design/).

## What it does

Runs [`scripts/apply-settings.py`](../scripts/apply-settings.py) against every repo in the org.
The script reads `settings.yml` and PATCHes any drift in merge methods, branch protection, and
rulesets. It triggers:

- **Weekly** — Mondays 06:00 UTC (catches drift / settings reverted via the GitHub UI).
- **On demand** — `workflow_dispatch` from the Actions tab.
- **On repo creation** — a `repo-created` `repository_dispatch` event.

## Authentication

The workflow authenticates as a **GitHub App** (`swimblocks-reconciler`), not a personal token.
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
8. Trigger the workflow via `workflow_dispatch` and confirm the `create-github-app-token` and
   `Apply settings` steps both pass.

## Rotate the private key

If the key is compromised or expiring:

1. App settings → **Private keys → Generate a private key** (you can have two active at once).
2. Replace the `APP_PRIVATE_KEY` secret on `swimblocks/.github` with the new `.pem` contents.
3. Run the workflow to confirm it still authenticates.
4. Delete the old key from the app's settings page.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `create-github-app-token` step fails | `APP_ID` / `APP_PRIVATE_KEY` secret missing or malformed, or the app isn't installed on the org. |
| `No repos found` | App lacks Metadata read, or isn't installed on the repos. |
| `SKIP branches.<branch>` on a private repo | Expected: GitHub Free disallows branch protection on private repos. Promote the repo to public to enable it. |
| Ruleset apply fails on a public repo | App lacks Administration write, or the ruleset payload in `settings.yml` is malformed. |
