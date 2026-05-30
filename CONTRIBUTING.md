# Contributing to SwimBlocks projects

These are the shared development standards for every repository in the
[SwimBlocks](https://github.com/swimblocks) organization. Individual repos may add a local
`CONTRIBUTING.md` with project-specific notes, but everything here applies unless a repo
explicitly overrides it.

> **Note for AI agents:** read this file before making changes. It is the source of truth for
> how work flows through these repos. See also the scope note under "Project scope" below —
> do not generalize Canada-specific features to other countries unless an issue asks for it.

## Core principles

- **Test-driven.** New functionality ships with tests. All tests pass before a change is
  considered done.
- **Small, reviewable changes.** Prefer focused PRs over sprawling ones.
- **Docs travel with code.** User-facing changes update the README / docs in the same PR.
  New code carries clear docstrings.
- **Simplicity.** If a change adds complexity, consider refactoring for clarity instead.

## Workflow: issue → branch → PR → squash-merge

1. **Open an issue first.** Describe the problem or feature. This is the unit of work.
2. **Branch** off `main`, named `<issue-number>-<short-slug>` (e.g. `42-fix-date-parsing`).
3. **Do the work.** Keep commits coherent. Run tests + lint locally before pushing.
4. **Open a PR** whose description includes `Closes #<issue-number>` and explains the *why*.
5. **CI must be green** (lint + tests) before merge.
6. **Hand off for review.** When an **agent** opens the PR, it stops here and gives the author
   a short summary — what changed, why, test/lint results, and the PR link — then waits. Agents
   do **not** self-merge.
   - *Exception:* large mechanical changes spanning many repos (e.g. an org-wide rename like
     dropping the `canswim` prefix) may be agent-merged to avoid dozens of round-trips, by
     prior agreement with the author.
7. **Review & squash-merge.** The author reviews the PR and squash-merges it themselves, then
   deletes the branch. The squash commit message should carry the meaningful detail, not just
   the PR title.

Direct pushes to `main` are discouraged; go through a PR. Never use `--no-verify` or bypass
signing. Create new commits rather than amending already-pushed ones.

## Quality gates

- **Lint:** Python repos use [ruff](https://docs.astral.sh/ruff/) with `select = ["E","F","I","W"]`.
  Run `ruff check .` (and `ruff check --fix .` to auto-fix) before pushing.
- **Tests:** `pytest -q`. Add coverage for new behaviour and regressions.
- **CI:** Python repos call the shared reusable workflow — see
  [`.github/workflows/reusable-python-ci.yml`](.github/workflows/reusable-python-ci.yml).
  A repo's own `ci.yml` should be a thin caller:

  ```yaml
  jobs:
    ci:
      uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main
  ```

## Dependencies

- `requirements.txt` holds **direct** runtime + test dependencies only, UTF-8, with `>=`
  minimums. Let pip resolve transitive deps; don't pin the whole `pip freeze` output.
- Dev-only tools (e.g. `ruff`) go in `requirements-dev.txt`, which layers on `requirements.txt`.
- Dependabot config lives **per repo** at `.github/dependabot.yml` (GitHub has no org-wide
  Dependabot inheritance). Weekly pip + github-actions updates is the default.

## Secrets & data

- Never commit secrets (`.env`, credentials, service-account keys) — they're gitignored.
- Never commit real personal data (officials' names/emails, club contact lists). Treat any
  such CSV/PDF as local sample data and gitignore it, or scrub before committing.

## Repo settings (org-wide policy)

Every SwimBlocks repo's GitHub settings are governed by
[`.github/settings.yml`](.github/settings.yml) in this repo. That file is the **single source
of truth**; the table below is a human-readable summary.

| Setting | Value | Why |
|---|---|---|
| `allow_squash_merge` | `true` | Squash is the only allowed merge method. |
| `allow_merge_commit` | `false` | No merge commits — keeps main linear. |
| `allow_rebase_merge` | `false` | No rebase merges either. |
| `squash_merge_commit_title` | `PR_TITLE` | Squash commit subject = PR title. |
| `squash_merge_commit_message` | `PR_BODY` | Squash commit body = PR description (so the body must be substantive). |
| `delete_branch_on_merge` | `true` | Branch deleted automatically after merge. |
| `allow_update_branch` | `true` | "Update branch" button enabled on PRs. |

### Branch protection (same source of truth)

`settings.yml` also carries a `branches:` section that the reconciler applies to every repo's
default branch via `PUT /repos/.../branches/main/protection`. Today that's:

- Pull request required (1 approving review, code-owner review required, stale reviews
  dismissed on new pushes).
- Linear history required (i.e. squash-only — pairs with the merge-method settings above).
- No force pushes, no deletions, no unresolved conversations at merge time.
- `enforce_admins: false` — the admin (you) keeps an override so a single-admin org doesn't
  deadlock approving its own PRs. Tighten this once another code owner exists.

> **Private-repo caveat:** GitHub Free does not allow branch protection on private repositories.
> The reconciler will skip and report this as a known limitation; the repo remains aligned on
> all the merge-method fields. Either upgrade the plan or flip the repo to public to enable
> protection.

### How it's enforced

- **`.github/workflows/reconcile-repo-defaults.yml`** — a scheduled Actions workflow that runs
  weekly, on `workflow_dispatch`, and on a `repo-created` `repository_dispatch` event. It reads
  `settings.yml` and PATCHes any drift on every repo in the org. (Requires a repo secret
  `SWIMBLOCKS_ADMIN_TOKEN` with admin rights on org repos.)
- **[`CODEOWNERS`](CODEOWNERS)** + branch protection on `main` (now also in `settings.yml`) —
  `settings.yml` and the reconciler workflow can only change via a PR that the designated
  admin reviews.

### Creating a new repo

**Always use the helper, not the GitHub UI**, so the new repo inherits the canonical settings:

```bash
scripts/create-repo.sh <repo-name> --description "Short About line"
```

The script **defaults to `--private`** because SwimBlocks repos usually start that way and
graduate to public later. While the repo is private, branch protection won't be applied
(GitHub Free disallows it on private repos); the reconciler will report this as a SKIP, which
is the expected steady state until you promote the repo.

After creation, add the new repo to the [org profile README](profile/README.md) and file
issues against it to add CI (calling the shared reusable workflow), `.github/dependabot.yml`,
and a per-repo `AGENTS.md`.

### Promoting a repo to public

When a repo is ready to release, **always use** [`scripts/make-public.sh`](scripts/make-public.sh)
— never the GitHub UI:

```bash
scripts/make-public.sh swimblocks/<repo-name>
```

That script is the canonical place where we accumulate pre-public checks. Currently it:

1. Confirms the repo is currently private.
2. Clones the repo and scans the **working tree** for secret-shaped strings (AWS keys, PEM
   private keys, GitHub PATs, Google OAuth client secrets, Slack tokens, embedded URL
   credentials, `api_key=...` etc.).
3. Scans the **git history** for the same (skip with `--skip-history` at your own risk).
4. Warns if `LICENSE` or `README.md` is missing.
5. Asks for typed confirmation.
6. Flips visibility via `gh repo edit --visibility public`.
7. Polls until GitHub releases the visibility-flip lock.
8. Re-runs `apply-settings.py`, which now installs branch protection.

**When we learn something new is required before a repo can safely go public, that check goes
into `make-public.sh`** rather than being remembered. Treat the script as a living checklist.

### Re-aligning an existing repo

If a repo's settings have drifted (or someone clicked through the GitHub UI), wait for the
next scheduled reconciler run, or trigger it manually from the Actions tab on `swimblocks/.github`.

## Project scope

SwimBlocks tools target **Swimming Canada's ecosystem and Canadian provincial associations**.
Some repos are hard-locked to Canadian data sources (e.g. `rems-sync`, `swim-club-tech-survey`);
others are Canada-default but architecturally extensible (e.g. `deck-eval-parser` templates).
Don't generalize features to other countries unless an issue explicitly requests it.
