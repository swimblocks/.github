# 0004 — uv as the org Python toolchain

Status: proposed

Tracking issue: [#33](https://github.com/swimblocks/.github/issues/33). Supersedes the
*mechanism* in [0002](0002-venv-standard.md); the rule it established stands.

## Context

[0002](0002-venv-standard.md) settled *whether* to use a venv (yes in persistent or shared
environments, no on ephemeral CI runners) and assumed the tooling was `python -m venv` +
`pip install -r requirements-dev.txt`. That has two costs:

- **The venv is manual.** It has to be created, activated (a different command on PowerShell
  than on Linux/macOS), and remembered. The failure mode 0002 was written to prevent —
  dependencies pip-installed into the global interpreter — is one forgotten `activate` away.
- **Nothing is locked.** `requirements.txt` holds direct `>=` minimums and lets pip resolve
  the rest, so two clones (or a clone and CI) can test different transitive versions.
  [`pyproject.toml`'s ruff comment](../../pyproject.toml) records this biting: an unpinned tool
  release turned a green `main` red on untouched code.

`swimblocks/officials-admin` ([#9](https://github.com/swimblocks/officials-admin/issues/9))
specifies [`uv`](https://docs.astral.sh/uv/) and is the first repo that would otherwise
diverge from this standard. Rather than record it as an exception (#33's option 3) or make
it export `requirements-dev.txt` from `uv` (option 2), the decision is to move the org to
`uv`: it satisfies the rule 0002 cares about *by construction* rather than by discipline.

## Design

### The standard

Python repos manage dependencies with `uv`:

- **`pyproject.toml`** declares them. Runtime deps under `[project] dependencies`; dev-only
  tools (`pytest`, `ruff`) under `[dependency-groups] dev`. Direct dependencies keep the `>=`
  minimums policy from `requirements.txt`.
- **`uv.lock` is committed.** It carries the transitive pins, so "no transitive pins" from the
  old policy becomes "no *hand-written* transitive pins" — the lockfile is where they live, and
  nobody edits it by hand.
- **Repos that are scripts, not installable packages** omit `[build-system]`; `uv` then does
  not try to build or install the project itself. `name`, `version` and `requires-python` are
  still required in `[project]`.

The commands, identical locally and in CI:

```bash
uv sync            # create/refresh .venv from uv.lock (installs the dev group)
uv run ruff check .
uv run pytest -q
```

### What happens to the venv rule

The rule from 0002 — *don't install project dependencies into a shared interpreter* — stands
unchanged. What changes is who enforces it. `uv sync` and `uv run` always operate on the
project's `.venv` (already gitignored org-wide), creating it when it is missing. There is
nothing to activate, so there is no "which Python am I in?" ambiguity to prevent, and
`pip install` into the global interpreter is simply not part of any documented flow.

0002's second half — *no venv on ephemeral CI* — is superseded for `uv` repos. `uv sync` builds
a `.venv` on the runner too, which costs nothing; the value of "CI installs globally" was only
that a venv was extra steps, and there are no extra steps here. One command path everywhere is
worth more than the exception.

### Reusable CI

[`reusable-python-ci.yml`](../../.github/workflows/reusable-python-ci.yml) **detects** the
tooling from the caller's checkout instead of taking a flag: a committed `uv.lock` selects the
`uv` path (`astral-sh/setup-uv`, then `uv sync --locked`); its absence selects the legacy pip
path exactly as before. Detection means a repo migrates by committing a lockfile — there is no
second PR against the shared workflow, and no window where a caller's CI is misconfigured.

`--locked` is deliberate: it fails when `uv.lock` disagrees with `pyproject.toml`, so a PR that
edits dependencies without re-locking goes red rather than testing stale pins.

`astral-sh/setup-uv` publishes exact tags only (no floating `v10`), so it is pinned to a
release; the `github-actions` Dependabot ecosystem keeps it current.

### Dependabot

Dependabot has a first-class `uv` ecosystem. Repos on `uv` replace their weekly `pip` entry
with `uv` (keeping `github-actions`). The canonical org-wide Dependabot configuration is
[#16](https://github.com/swimblocks/.github/issues/16); it should treat `pip` and `uv` as
alternatives per repo, not require both.

### Devcontainers

The pattern from 0002 is unchanged in intent — the devcontainer lands a contributor or agent
in the documented environment with no manual step — but `postCreateCommand` becomes `uv sync`
instead of creating a venv and pip-installing. How `uv` reaches the image (a devcontainer
feature, or the official installer) is left to each repo. The first repo to adopt this,
`officials-admin`, will land a concrete, built-and-tested snippet, which should then be folded
back into [`CONTRIBUTING.md`](../../CONTRIBUTING.md#environments-uv).

## Rollout

- **New Python repos start on `uv`.**
- **Existing repos keep working as they are.** The reusable CI's legacy path means nothing
  breaks on merge. Each repo (`deck-eval-gen`, `rems-sync`, and `.github` itself, which still
  has a `requirements-dev.txt` and a pip devcontainer) migrates under its own follow-up issue,
  as 0002's rollout did: add `pyproject.toml` deps, commit `uv.lock`, delete the requirements
  files, update the devcontainer and the Dependabot entry.
- `swim-club-tech-survey` and `deck-eval-parser`, which never had a `requirements-dev.txt`,
  no longer need one as a prerequisite — a `pyproject.toml` dev group is the migration.
- **`officials-admin` is the first `uv` repo**, and its CI is the first real exercise of the
  reusable workflow's `uv` path.

## Verification

- `uv sync --locked`, `uv run ruff check .` and `uv run pytest -q` succeed on a project laid
  out as above, and `uv sync --locked` exits non-zero after `pyproject.toml` gains a dependency
  the lockfile lacks. (Checked with uv 0.12 on a scratch project while writing this.)
- `actionlint` passes on the revised `reusable-python-ci.yml`.
- **Not yet verified:** the workflow's `uv` path on a real runner. That happens the first time
  a `uv.lock` repo calls it — `officials-admin` under #9. The pip path is the pre-existing
  steps behind an `if:`, and this repo's own `ci.yml` continues to exercise it.

## Open items

- The exact devcontainer snippet, as above.
- Legacy-path removal: once no org repo is on `requirements-dev.txt`, drop the pip path and
  the `requirements-file` input from the reusable workflow. Until then each is one more thing
  a reader must ignore; the cost is accepted for a non-breaking rollout.
- `rollout.yml` still `pip install`s this repo's `requirements.txt`. It is an ephemeral runner
  running a script, so it does not need to move until `.github` migrates.
