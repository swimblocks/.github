# 0002 — venv standard + devcontainer provisioning

Status: implemented

## Context

venv usage is inconsistent across SwimBlocks repos. A survey of every org repo (2026-06) found
that every Python repo's README documents `python -m venv .venv`, but **none automate or enforce
it**: there are no devcontainers in the working repos, and `.github`'s devcontainer (the one
container that exists) installs nothing into a venv. The practical symptom: while debugging the
reconciler, dependencies (`ruff`, `pytest`, `requirements-dev.txt`) were pip-installed into the
Codespace's global Python, because nothing established a project venv. "Which Python am I in?"
was ambiguous.

| Repo | Devcontainer | venv in README | requirements-dev.txt |
|---|---|---|---|
| `.github` | yes (no venv) | via org AGENTS.md | added in #27 |
| `swim-club-tech-survey` | no | yes | no |
| `deck-eval-gen` | no | yes | yes |
| `deck-eval-parser` | no | yes | no (chose "no linter") |
| `rems-sync` | no | yes | yes |
| `rems-sync-apps-script` | — | — | JavaScript (N/A) |

## Design

### The rule

Whether to use a venv depends on whether the environment is **persistent/shared** or
**ephemeral/single-purpose**:

- **Persistent or shared → use a venv.** A developer laptop or a devcontainer/Codespace hosts
  many projects and outlives any single task. Installing project deps into the global interpreter
  causes cross-project version conflicts and can shadow system tools. Create and activate
  `.venv` (already gitignored org-wide), then `pip install -r requirements-dev.txt`.
- **Ephemeral, single-job → no venv.** A GitHub Actions runner is a throwaway VM dedicated to one
  job; the machine itself is the isolation. A venv there adds steps and buys nothing. The reusable
  CI (`reusable-python-ci.yml`) and the reconciler workflow correctly install globally.

This is not "venv everywhere" or "venv nowhere" — it's venv in any environment that is reused or
shared, and skip it only where the whole environment is already disposable and single-purpose.

### `.github` implementation (option B)

The `.github` devcontainer is made to dogfood the documented flow rather than be an exception. Its
`postCreateCommand` creates `.venv` and installs `requirements-dev.txt`, so a contributor (or
agent) who opens the repo in a Codespace lands in exactly the environment `AGENTS.md` prescribes,
with no manual step. `requirements-dev.txt` is supplied by [#27](https://github.com/swimblocks/.github/issues/27).

### Org-wide rule capture

The rule is folded into `CONTRIBUTING.md` and `AGENTS.md` via the "capture review-derived rules
here" mechanism, so it binds future contributors and agents rather than living only in this doc.

## Rollout to the other repos

Each Python repo gets its own follow-up issue to add a venv-provisioning devcontainer matching the
`.github` pattern. `swim-club-tech-survey` and `deck-eval-parser` need a `requirements-dev.txt`
first (prerequisite noted in their issues). `rems-sync-apps-script` is excluded — it's JavaScript,
so the venv standard does not apply.

## Verification

- Building the `.github` devcontainer produces a `.venv` with `ruff` + `pytest` importable, with no
  manual `pip install`.
- `.venv` is gitignored (already true org-wide) and never committed.
- CI is unchanged and still venv-free (ephemeral runner).

## Open items

- The reusable CI uses `cache: pip` without `cache-dependency-path`; it works today only because
  caller repos have a `requirements.txt`. Not in scope here — tracked separately if it bites a
  dev-deps-only repo.
