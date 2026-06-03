# Contributing to SwimBlocks projects

These are the shared development standards for every repository in the
[SwimBlocks](https://github.com/swimblocks) organization. Individual repos may add a local
`CONTRIBUTING.md` with project-specific notes, but everything here applies unless a repo
explicitly overrides it.

> First time setting up locally? Read [`docs/development.md`](docs/development.md)
> for the recommended layout, the user-local agent pointer files, and the install script.

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
- **Capture review-derived rules here.** When a code review (or any maintainer conversation)
  yields a generalizable rule about how SwimBlocks repos should be developed, fold it into
  this file via a PR closing a tracking issue. A verbal "I'll remember" doesn't bind future
  contributors — agents especially. The rules below grew this way; new ones should land the
  same way.

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

### Solo-admin merge path

Until a second code owner exists, the author satisfying `require_code_owner_reviews` on their
own PR is mathematically impossible (GitHub blocks self-approval). Two options, both relying
on admin bypass in the repo ruleset (see [`settings.yml`](.github/settings.yml)):

- **Web UI:** on the PR page, scroll past the standard "Squash and merge" button to the
  "Merge without waiting for requirements to be met (bypass branch protections)" link, and
  confirm.
- **CLI:** `gh pr merge <N> --repo swimblocks/<repo> --admin --squash --delete-branch`.

This is the deliberate steady state for a single-admin org. Revisit when a second code owner
joins.

Direct pushes to `main` are discouraged; go through a PR. Never use `--no-verify` or bypass
signing. Create new commits rather than amending already-pushed ones.

### Code comments

- **TODO / aspirational comments must link to a GitHub issue.** A comment that says "out of
  scope for now" or "should add X later" is just a wish; the next reader (human or agent)
  has no way to act on it. Open a tracking issue and reference it inline:

  ```python
  # See https://github.com/swimblocks/<repo>/issues/42 for the proper solution;
  # the regex below is the cheap stopgap.
  ```

  Same rule for shell, YAML, etc. If you don't have an issue number yet, file one before the
  PR lands. Reviewers will (and have!) push back on bare TODOs.

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

**Public repos** use GitHub Rulesets (`rulesets:` block in `settings.yml`). Rulesets support
bypass actors, so org owners and repo admins can force-push when genuinely needed (see
[Force-push break-glass](#force-push-break-glass) below). The ruleset enforces:

- Pull request required (1 approving review, code-owner review required, stale reviews
  dismissed on new pushes, all threads resolved).
- Linear history required (squash-only — pairs with the merge-method settings above).
- No force pushes or deletions for non-admins.

**Private repos** fall back to the legacy `branches:` protection block. GitHub Free does not
allow branch protection on private repositories, so the reconciler skips it and reports it as a
known limitation; the repo remains aligned on all the merge-method fields. Either upgrade the
plan or flip the repo public to enable protection.

### Force-push break-glass

Org owners and repo admins are listed as bypass actors in the ruleset, so a force-push
(needed for a history rewrite, purging a file that shouldn't have been committed, etc.) is just:

```bash
git push origin main --force
```

No UI changes, no disabling protection first. GitHub records the bypass in the org audit log.
This only works on public repos (rulesets); private repos have no protection at all on Free.

### How it's enforced

- **`.github/workflows/reconcile-repo-defaults.yml`** — a scheduled Actions workflow that runs
  weekly, on `workflow_dispatch`, and on a `repo-created` `repository_dispatch` event. It reads
  `settings.yml` and PATCHes any drift on every repo in the org. It authenticates as a GitHub App
  (secrets `APP_ID` + `APP_PRIVATE_KEY`); see [`docs/reconciler.md`](docs/reconciler.md) for how it
  works, the app's permissions, and the setup / key-rotation runbook.
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
