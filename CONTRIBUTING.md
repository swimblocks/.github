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

## Project scope

SwimBlocks tools target **Swimming Canada's ecosystem and Canadian provincial associations**.
Some repos are hard-locked to Canadian data sources (e.g. `rems-sync`, `swim-club-tech-survey`);
others are Canada-default but architecturally extensible (e.g. `deck-eval-parser` templates).
Don't generalize features to other countries unless an issue explicitly requests it.
