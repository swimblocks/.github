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
   See [the `no-issue` exception](#the-no-issue-exception) for changes small enough to
   skip this.
2. **Branch** off `main`, named `<issue-number>-<short-slug>` (e.g. `42-fix-date-parsing`),
   or a descriptive slug when there is no issue.
3. **Do the work.** Keep commits coherent. Run tests + lint locally before pushing.
4. **Read the change before it becomes a PR.** A pull request is a claim that its author
   stands behind the change, so nobody opens one carrying work the author hasn't actually
   read. Run `git diff main...` and read it. This is where debug output, stray files, and
   data or credentials that were never meant to be committed get caught.
   - When an **agent** made the change, the author hasn't seen it yet — so the agent stops
     *before* opening the PR. It pushes the branch, posts a short summary (what changed, why,
     lint/test results), and waits. The author reviews locally, then opens the PR or asks the
     agent to.
   - An agent that is unsure about a decision raises it with the author **here**, not in the
     PR description. A question written into a PR reads as though the author is asking their
     reviewers, which sponsors a question they never asked.
5. **Open a PR** that explains the *why* and names its issue. A PR that finishes the issue
   says `Closes #<issue-number>`. One that lands self-contained progress and leaves more to do
   says `Refs #<issue-number>`, and the issue stays open. A `no-issue` PR has no number to
   close, and carries the `NO-ISSUE:` trailer instead. See [Sizing a PR](#sizing-a-pr).
6. **CI must be green** (lint + tests) before merge.
7. **Hand off for merge.** Agents do **not** self-merge: after CI is green, post the PR link
   and stop.
   - *Exception:* large mechanical changes spanning many repos (e.g. an org-wide rename like
     dropping the `canswim` prefix) may be agent-opened and agent-merged to avoid dozens of
     round-trips, by prior agreement with the author.
8. **Review & squash-merge.** The author reviews the PR and squash-merges it themselves, then
   deletes the branch. The squash commit message should carry the meaningful detail, not just
   the PR title.

### Sizing a PR

Keep PRs reasonably sized, and err toward smaller. One issue can take several PRs, each on its
own branch. Ship a self-contained piece rather than let a branch sprawl. Good places to cut:

- a test harness or fixtures land before the fixes they drive;
- a module is complete and reviewable before later modules build on it;
- a design decision is worth review before implementation continues.

Each PR stands on its own: tests pass and `main` works once it merges. The last one closes the
issue.

### The `no-issue` exception

A change small enough to explain itself — a typo, a doc clarification, recording a decision
already made — may go straight to a PR. Label it `no-issue` and end the description with a
trailer saying why:

```
NO-ISSUE: Clarifying Documentation
```

The ceremony in step 1 is worth paying whenever a change needs a decision recorded, argued,
or found again later. It is pure overhead when the change carries its own justification in
one paragraph. The label and the trailer are what keep the exception **visible and
auditable** rather than silent: every PR that skipped the issue says so, in a form you can
search for.

Use a real issue whenever the change needs discussion, has acceptance criteria, or is
something a future reader would look for in the tracker. Changes to the rules in this file
are always in that category — a policy that nobody can find the reasoning for is a policy
that gets re-litigated.

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

### Naming files and directories

**`snake_case` for directories and source files. `kebab-case` for anything executable,
repo names, documentation, and spellings an ecosystem has fixed.**

- **`snake_case`** — directories, and source files in any language: `rules_engine/`,
  `apply_settings.py`, `test_apply_settings.py`.
- **`kebab-case`** — anything executable; repo names; documentation
  (`0004-uv-standard.md`); ecosystem-fixed spellings (`requirements-dev.txt`).
- **Leave alone** what a tool dictates: `README.md`, `CODEOWNERS`, `ISSUE_TEMPLATE/`,
  `__init__.py`, `pyproject.toml`.

**"Executable" means the executable bit is set in the filesystem**, not that something
happens to be runnable via an interpreter — `scripts/apply_settings.py` is a source
file, not an executable. Ruff's `EXE` rules keep a `.py` file's shebang and bit in
agreement.

## Quality gates

- **Lint (Python):** Python repos use [ruff](https://docs.astral.sh/ruff/) with `select = ["E","EXE","F","I","W"]`.
  Run `uv run ruff check .` (and `uv run ruff check --fix .` to auto-fix) before pushing.
- **Lint (Go):** Go repos use [golangci-lint](https://golangci-lint.run/) v2, configured by a
  committed `.golangci.yml`. Every Go repo carries the same one, unchanged:

  ```yaml
  version: "2"
  linters:
    default: all
    disable:
      # Contradict the Google Go Style Guide.
      - decorder          # orders declarations by kind; the guide orders them for the reader
      - err113            # a sentinel for every error; the guide: only when callers must tell errors apart
      - exhaustruct       # every field set; the guide: make the zero value useful
      - exhaustruct_v5
      - funcorder         # exported methods first; the guide orders for the reader
      - noinlineerr       # forbids `if err := f(); err != nil`, an idiom the guide uses
      - nonamedreturns    # the guide allows named results where they document
      - paralleltest      # t.Parallel() everywhere; tparallel checks the tests that do use it
      - perfsprint        # trades clarity for speed; the guide puts clarity first
      - prealloc          # likewise
      - testpackage       # black-box tests only; in-package tests are normal Go
      - varnamelen        # long names in small scopes; the guide prefers short ones there
      - wrapcheck         # wrap every error; the guide: wrap when it adds context
      # Size and repetition thresholds.
      - cyclop
      - dogsled
      - dupl
      - funlen
      - gocognit
      - goconst
      - gocyclo
      - interfacebloat
      - lll
      - maintidx
      - mnd
      - nestif
      # Blank lines and alignment: the formatter's business.
      - nlreturn
      - tagalign
      - whitespace
      - wsl
      - wsl_v5
      # Mean nothing until the org writes their configuration.
      - depguard          # which packages may be imported
      - goheader          # a required file header
      - gomodguard        # which modules may be required
      - gomodguard_v2
      - grouper           # whether declarations are grouped
      - importas          # required import aliases
      # Other.
      - godox             # flags every TODO, including those that link an issue as CONTRIBUTING requires
      - tagliatelle       # one casing for struct tags; wire formats follow the spec they implement
    settings:
      exhaustive:
        default-signifies-exhaustive: true   # a `default:` case is a deliberate choice
      gosec:
        excludes: [G104]                     # unchecked errors: errcheck's job already
      nolintlint:
        require-explanation: true
        require-specific: true
      revive:
        enable-default-rules: true
        rules:
          - name: unused-parameter           # fires on every handler whose signature is fixed
            disabled: true
    exclusions:
      rules:
        # In a test, a panicking type assertion is the test failing, and test inputs aren't attacker-controlled.
        - path: _test\.go
          linters: [forcetypeassert, gosec]
  formatters:
    enable: [gofmt, goimports]
  ```

  **Every linter is on unless the disable list says why not.** A linter is off only if it
  contradicts the [Google Go Style Guide](https://google.github.io/styleguide/go/), is a size
  or repetition threshold, is a blank-line or alignment preference, or means nothing until the
  org writes configuration for it. A linter for a library we don't use stays on; it is silent
  until the library arrives. The disable list is the only record of what is off, and a change
  to it, or to anything else in this file, is a change to the org standard, made here.

  **A finding that is wrong in context is suppressed on its line, with the reason** —
  `//nolint:bodyclose // the call owns the response and closes it in close()` — not by
  switching the linter off. `nolintlint` rejects a suppression that names no linter or gives no
  reason, so every suppression records a judgement. How to answer the findings that take
  judgement, and when suppressing is right: [Go style guide](docs/styleguide/go.md#lint-findings).
  The weekly calibration report
  ([design 0007](docs/design/0007-review-standard.md#calibration-report)) reads them to
  suggest changes to this list.

  Run `golangci-lint run` (and `golangci-lint run --fix` to auto-fix) before pushing.
- **Tests:** `uv run pytest -q`; in Go repos, `go test ./...`. Add coverage for new behaviour
  and regressions.
- **CI:** each repo calls the shared reusable workflow for its language —
  [`reusable-python-ci.yml`](.github/workflows/reusable-python-ci.yml) or
  [`reusable-go-ci.yml`](.github/workflows/reusable-go-ci.yml). A repo's own `ci.yml` should
  be a thin caller:

  ```yaml
  jobs:
    ci:
      uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main   # or reusable-go-ci.yml
  ```

  The Go workflow checks `go mod tidy -diff`, then runs `go build ./...`, `go test -race ./...`
  and golangci-lint at a pinned version. Repo-specific gates (a coverage floor, an image
  build) go in further jobs in the repo's own `ci.yml`, beside the call.

## Code review

Code follows the org style guide in [`docs/styleguide/`](docs/styleguide/README.md): the lint
set above, a few points for every language, then one file per language, built on Google's
[Go](https://google.github.io/styleguide/go/) and
[Python](https://google.github.io/styleguide/pyguide.html) style guides. A review comment that
applies one of its points names the point's ID (`go/errors`), so the author can check the
reasoning.

**Automatic readability review.** Each repo calls the shared
[`reusable-readability-review.yml`](.github/workflows/reusable-readability-review.yml) from its
own `.github/workflows/readability-review.yml`, separate from `ci.yml` because it runs on
different events. That file is a copy of
[`workflow-templates/readability-review.yml`](workflow-templates/readability-review.yml).
[`scripts/create-repo.sh`](scripts/create-repo.sh) commits it to every new repo's default branch,
and GitHub offers it under a repo's **Actions → New workflow**. Add it to an existing repo in
a pull request of its own: Claude Code Action runs only once the caller is on the default
branch, so a pull request that adds it alongside other changes fails its review check.

A pull request is reviewed once, when it is opened or marked ready for review, against the style
guide for the languages it changes. Findings are inline comments from the Claude GitHub App, and
the review ends with a summary comment saying how many it posted. It runs again on each push
only to confirm the review has happened. Drafts, fork pull requests and pull requests from bots
are skipped. It needs only the Claude GitHub App on the repo: the model token is read from
Google Cloud over OIDC, and the two secrets that say where to find it are copied into every repo
by the settings rollout ([`docs/reconciler.md`](docs/reconciler.md)). What it needs, how to
operate it and what to do when it fails: [`docs/readability-review.md`](docs/readability-review.md).

**Automatic security review.** Each repo also calls the shared
[`reusable-security-review.yml`](.github/workflows/reusable-security-review.yml) from its own
`.github/workflows/security-review.yml`, a copy of
[`workflow-templates/security-review.yml`](workflow-templates/security-review.yml), which
`create-repo.sh` also commits. It checks each pull request against the
[security guide](docs/security/README.md), one check per rule, such as `security / secrets`.
How it runs and what to do when it fails: [`docs/security-review.md`](docs/security-review.md).

Answer every finding: change the code, or reply saying why not, then resolve the thread.
A finding you reject is as useful as one you accept: the weekly calibration report
([design 0007](docs/design/0007-review-standard.md#calibration-report)) counts both, to
reword the guide or move a point into lint. Your reply is its record of why.

## Dependencies

- Python repos use [`uv`](https://docs.astral.sh/uv/). **Direct** runtime dependencies go in
  `pyproject.toml` under `[project] dependencies`, with `>=` minimums; dev-only tools (e.g.
  `ruff`, `pytest`) go in `[dependency-groups] dev`. Don't hand-write transitive pins.
- **Commit `uv.lock`.** It is where the transitive pins live, so a clone and CI test the same
  versions. Never edit it by hand; change dependencies with `uv add` / `uv remove` (or edit
  `pyproject.toml` and run `uv lock`). CI runs `uv sync --locked`, which fails a PR whose
  `pyproject.toml` and `uv.lock` disagree.
- A repo that is scripts rather than an installable package omits `[build-system]`.
- **Legacy repos** still on `requirements.txt` / `requirements-dev.txt` keep working: the shared
  CI runs the pip flow whenever there is no `uv.lock`. New repos start on `uv`; existing ones
  migrate under their own issue. See
  [`docs/design/0004-uv-standard.md`](docs/design/0004-uv-standard.md).
- Go repos use Go modules. **Commit `go.mod` and `go.sum`**, and don't vendor. Change
  dependencies with `go get` and `go mod tidy`; CI runs `go mod tidy -diff`, which fails a PR
  whose `go.mod` or `go.sum` is out of date. The module path is `github.com/swimblocks/<repo>`.
- Dependabot config lives **per repo** at `.github/dependabot.yml` (GitHub has no org-wide
  Dependabot inheritance). Weekly `uv` (or `pip`, for a legacy repo) + github-actions updates
  is the default; Go repos use `gomod` + github-actions, plus `docker` when there is a
  `Dockerfile`.

## Environments (uv)

A developer laptop or a devcontainer/Codespace hosts many projects and outlives any single task,
so **project dependencies never go into the global interpreter** — global installs cause
cross-project conflicts.

`uv` makes that the default rather than something to remember: `uv sync` and `uv run` always
work inside the project's `.venv` (gitignored org-wide), creating it when it's missing. There is
no activation step, on any OS. The same commands run locally and in CI:

```bash
uv sync                 # create/refresh .venv from uv.lock
uv run ruff check .
uv run pytest -q
```

A repo's devcontainer should run `uv sync` via `postCreateCommand`, so a contributor (or agent)
lands in the documented environment with no manual step.

Rationale and the cross-repo rollout are in
[`docs/design/0004-uv-standard.md`](docs/design/0004-uv-standard.md); it supersedes the pip
mechanism, and the no-venv-on-CI exception, in
[`0002`](docs/design/0002-venv-standard.md).

## Environments (Go)

Go repos build on **the current stable Go release**. The standard names no version number;
in each repo, `go.mod`'s `go` directive is the single source of truth. CI reads it, and nobody
repeats the version anywhere else. Go supports the two most recent releases, so a repo moves
to a new one within six months of its release; Dependabot's `gomod` updates prompt it.

Go keeps dependencies in a per-user module cache rather than in a global install, so there is
nothing to isolate per project. The same commands run locally and in CI:

```bash
go build ./...
go test ./...
golangci-lint run
```

Install golangci-lint at the version [`reusable-go-ci.yml`](.github/workflows/reusable-go-ci.yml)
pins, so local results match CI's. Rationale, project layout and naming are in
[`docs/design/0005-go-standard.md`](docs/design/0005-go-standard.md).

A Go repo's `.devcontainer/devcontainer.json` uses the official Go feature, which installs
golangci-lint too:

```json
{
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/devcontainers/features/go:1": {
      "version": "latest",
      "golangciLintVersion": "2.15.0"
    }
  }
}
```

- `"version": "latest"` is the current stable release. When a repo's `go.mod` names a newer
  Go, the toolchain fetches it, so the version still lives only in `go.mod`.
- `golangciLintVersion` is the version `reusable-go-ci.yml` pins, written without the `v`.
  Change the two together. The feature installs golangci-lint only while its
  `installGoTools` option is on, as it is by default.

## Secrets & data

- Never commit secrets (`.env`, credentials, service-account keys) — they're gitignored.
  The security review scans each pull request for them, and public repos reject a push that
  carries one ([security guide](docs/security/README.md#secrets)).
- Never commit real personal data (officials' names/emails, club contact lists). Treat any
  such CSV/PDF as local sample data and gitignore it, or scrub before committing.

### Test fixtures: Faker is the standard

Our data is about real volunteers and real minors, so tests can't just use a trimmed-down
copy of production. Every repo needing realistic-looking people in fixtures uses
[Faker](https://faker.readthedocs.io/) — `faker>=30.0`, locale `en_CA`. Don't invent a
per-repo substitution scheme; a scheme nobody else recognises is a scheme nobody else audits.

The rules, and why each exists:

- **Seed Faker and record the seed.** Unseeded fixtures change every run, so a diff tells you
  nothing and a failure can't be reproduced. Same seed plus same Faker version gives identical
  output; if a Faker major bump shifts it, regenerate deliberately and say so in the commit.
- **Map each real value to one fake value, consistently**, keyed on something stable — a
  registry ID, not a name. Otherwise rows that referenced each other in the real data stop
  doing so in the fixture, silently destroying the thing under test.
- **Keep any real→fake mapping out of git.** It's useful for debugging a fixture row, and it is
  a re-identification table, so it belongs with your local secrets.
- **Faker doesn't know swimming.** Roles, club codes, credential and meet names come from a
  constrained vocabulary in the generator. Faker names a person; it does not name an
  `Inspector of Turns Evaluation #2`.
- **Keep the generator beside the fixture it writes**, with a `--help`, so regenerating is one
  command a reviewer can run rather than prose they have to trust.

**Prefer fully synthetic data** — generate the shape you need and there's no privacy problem
at all. Pseudonymize real data only when its real structure is the point, such as reproducing
a legacy system's behaviour where real dates and real credential combinations are exactly
what's under test. Then read only the columns you need: personal data you never fetched is
personal data you cannot leak, and it turns the reviewer's job into checking a column list
rather than inspecting a diff.

Dates and category combinations can still re-identify someone inside a small club even with
names removed. Say so in the fixture's README rather than implying pseudonymization made the
data anonymous.

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
| `secret_scanning` | `enabled` (public repos) | GitHub flags a committed credential. Free for public repos; GitHub Free doesn't offer it to private ones. |
| `secret_scanning_push_protection` | `enabled` (public repos) | GitHub rejects a push carrying a recognised secret, before it's public. |

### Branch protection (same source of truth)

**Public repos** use GitHub Rulesets (`rulesets:` block in `settings.yml`). Rulesets support
bypass actors, so org owners and repo admins can force-push when genuinely needed (see
[Force-push break-glass](#force-push-break-glass) below). The ruleset enforces:

- Pull request required (1 approving review, code-owner review required, stale reviews
  dismissed on new pushes, all threads resolved).
- Linear history required (squash-only — pairs with the merge-method settings above).
- The readability review's check, `review / review`, must pass
  ([`docs/readability-review.md`](docs/readability-review.md)).
- No force pushes or deletions for non-admins.

**Private repos** fall back to the legacy `branches:` protection block. GitHub Free does not
allow branch protection on private repositories, so the rollout skips it and reports it as a
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

- **`.github/workflows/release.yml`** — publishes a `settings-YYYY-MM-DD` release every Monday,
  pinning the version of `settings.yml` the org is on. Publishing it starts the rollout.
- **`.github/workflows/rollout.yml`** — checks out a released tag and PATCHes any drift on every
  repo in the org. It runs on every release, on `workflow_dispatch`, and on a `repo-created`
  `repository_dispatch` event.

  Each authenticates as its own GitHub App — `swimblocks-releaser` on `.github` alone for the
  release, `swimblocks-reconciler` across the org for the rollout — so neither holds a permission
  the other's scope would make dangerous. See [`docs/reconciler.md`](docs/reconciler.md) for the
  permissions, the secrets, and the setup / key-rotation runbook.
- **[`CODEOWNERS`](CODEOWNERS)** + branch protection on `main` (now also in `settings.yml`) —
  `settings.yml` and the workflows that apply it can only change via a PR that the designated
  admin reviews.

### Creating a new repo

**Always use the helper, not the GitHub UI**, so the new repo inherits the canonical settings:

```bash
scripts/create-repo.sh <repo-name> --description "Short About line"
```

The script **defaults to `--private`** because SwimBlocks repos usually start that way and
graduate to public later. While the repo is private, branch protection won't be applied
(GitHub Free disallows it on private repos); the rollout will report this as a SKIP, which
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
4. Scans every branch's history with [gitleaks](https://github.com/gitleaks/gitleaks) and
   [trufflehog](https://github.com/trufflesecurity/trufflehog). The script downloads each at a
   pinned release and checks its checksum, so there's nothing to install. gitleaks uses the
   org's rules, [`.gitleaks.toml`](.gitleaks.toml). A false positive is the repo's own
   exception, made in a pull request: its fingerprint in the repo's `.gitleaksignore`, or a
   `gitleaks:allow` or `trufflehog:ignore` comment on the line.
5. Warns if `LICENSE` or `README.md` is missing.
6. Asks for typed confirmation.
7. Flips visibility via `gh repo edit --visibility public`.
8. Polls until GitHub releases the visibility-flip lock.
9. Re-runs `apply_settings.py`, which now installs branch protection.

**When we learn something new is required before a repo can safely go public, that check goes
into `make-public.sh`** rather than being remembered. Treat the script as a living checklist.

### Re-aligning an existing repo

If a repo's settings have drifted (or someone clicked through the GitHub UI), wait for the next
weekly rollout, or run `rollout.yml` manually from the Actions tab on `swimblocks/.github`. For a
single repo, `python scripts/apply_settings.py swimblocks/<repo>` does the same thing locally.

## Project scope

SwimBlocks tools target **Swimming Canada's ecosystem and Canadian provincial associations**.
Some repos are hard-locked to Canadian data sources (e.g. `rems-sync`, `swim-club-tech-survey`);
others are Canada-default but architecturally extensible (e.g. `deck-eval-parser` templates).
Don't generalize features to other countries unless an issue explicitly requests it.
