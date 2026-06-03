# 0001 — GitHub App authentication for the reconciler workflow

Status: implemented

## Context

The `reconcile-repo-defaults` workflow authenticates to the GitHub API via a long-lived personal
access token stored as the `SWIMBLOCKS_ADMIN_TOKEN` repository secret. Long-lived PATs have three
problems:

1. **Manual rotation.** There is no automatic expiry; the token must be manually revoked and
   replaced when it expires or is suspected of compromise.
2. **Personal account coupling.** The token is tied to the org owner's personal account. If that
   account changes or loses org access, the workflow silently breaks.
3. **Overly broad scope.** Classic PATs grant wide permissions; fine-grained PATs are better but
   still long-lived.

GitHub Apps are the recommended replacement: they issue short-lived installation tokens (~1 hour
TTL) automatically at runtime, need no manual rotation, and are scoped at install time to exactly
the permissions the workflow requires.

## Design

### GitHub App

A GitHub App is registered on the `swimblocks` org with the minimum permissions the reconciler
needs:

| Permission | Level | Reason |
|---|---|---|
| Repository → Metadata | Read | Required by all API calls; auto-selected |
| Repository → Administration | Read & write | PATCH repo settings, PUT/DELETE branch protection, GET/POST/PUT rulesets |

No webhook is configured (the app is used purely for token generation, not event delivery).
The app is installed on **all repositories** in the org.

### Secrets

Two repository secrets replace `SWIMBLOCKS_ADMIN_TOKEN` on `swimblocks/.github`:

| Secret | Value |
|---|---|
| `APP_ID` | Numeric app ID shown on the app's settings page |
| `APP_PRIVATE_KEY` | Full contents of the `.pem` private key downloaded from the app's settings page |

### Workflow change

`actions/create-github-app-token@v1` is added as the first step in the `reconcile` job. It
authenticates as the app using the private key, fetches the org installation, and mints a
short-lived token. That token is passed as `GH_TOKEN` to subsequent steps.

```yaml
- uses: actions/create-github-app-token@v1
  id: app-token
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    owner: swimblocks
```

`SWIMBLOCKS_ADMIN_TOKEN` is no longer referenced in the workflow and its secret can be deleted
from the repository settings after the app is confirmed working.

The one-time app setup, key rotation, and troubleshooting steps are maintained as a living
playbook in [`docs/reconciler.md`](../reconciler.md) — not duplicated here, since this design doc
is an append-only record of the decision.

## Verification

- `create-github-app-token` step completes without error on a `workflow_dispatch` run.
- `Apply settings` step lists all org repos and patches/verifies each one.
- Org audit log shows API calls attributed to `swimblocks-reconciler[bot]`, not a personal account.

## Open items

- See [#20](https://github.com/swimblocks/.github/issues/20) — `actions/checkout@v4` and
  `actions/setup-python@v5` still run on Node.js 20 (forced to Node.js 24 on 2026-06-16).
