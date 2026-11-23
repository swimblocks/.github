# 0007 — Automatic readability review and a stricter Go lint set

Status: proposed

Tracking issue: [#68](https://github.com/swimblocks/.github/issues/68).

## Context

[0005](0005-go-standard.md) admits Go as an org language, with golangci-lint's `standard`
set as its lint baseline. That set catches bugs — unchecked errors, vet findings, dead code —
but says almost nothing about readability, and `swimblocks/fetch-service` is about to bring
the org its first substantial Go code. Nobody in the org has had their Go reviewed for
readability before, so the bar has to be written down rather than carried in someone's head.

Review today is whatever the maintainer and their agent notice. Nothing reviews a pull request
unless someone remembers to ask, and a review run in a local session leaves nothing on the
pull request.

Three layers, each doing what the others can't, and a loop that tunes them:

- **Linters** check what is mechanical, on every push, for free.
- **An org style guide** says what a reviewer checks beyond the linters.
- **An automatic readability reviewer** applies the style guide to every pull request without
  anyone remembering to ask, and leaves its findings on the pull request where they stay.
- **A calibration report** watches where the linters are overruled and where the reviewer's
  findings are accepted or rejected, and suggests changes to both. The two are tuned together:
  a style point that keeps being raised and accepted belongs in a linter, so the reviewer can
  spend its attention on what only judgement can catch.

Correctness, security and design review are deliberately out of the reviewer's scope: CI, the
agent's own pre-handoff review and the human reviewer cover them. A reviewer that does one
thing, with little context beyond the change and the style guide, does it better.

## Design

### Go lint set

**Everything is on unless there's a stated reason for it to be off.** The org `.golangci.yml`
enables every golangci-lint linter and names the exceptions, each under the reason it's off. A
linter is off only if it:

- contradicts the [Google Go Style Guide](https://google.github.io/styleguide/go/) or
  [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments);
- is a size or repetition threshold — "this does too much" is a judgement the reviewer makes
  better than a number does;
- is a blank-line or alignment preference, which is the formatter's business; or
- means nothing until the org writes configuration for it.

A linter for a library we don't use stays on: it is silent until the library arrives, and then
it is already checking. A linter that is wrong in a particular place is suppressed on that line,
with the reason — `//nolint:bodyclose // the call owns the response and closes it in close()` —
not switched off. `nolintlint` rejects a suppression that names no linter or gives no reason, so
every suppression is a recorded judgement, which is what the
[calibration report](#calibration-report) reads.

The org `.golangci.yml` becomes:

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

The disable list is the record of what is intentionally off; there is no other. golangci-lint's
version is pinned in CI (0005), so a linter added in a new release switches on in the pull
request that upgrades it, where its findings are seen and either fixed, suppressed or argued
into the disable list. As in 0005, a repo commits this file unchanged, and a change to it is a
change to the org standard.

#### Trial against `fetch-service`

All 115 golangci-lint linters (v2.15.0, Go 1.27.4) were run against `fetch-service`, the
org's first Go repo: an HTTP service with a handful of internal packages and command-line tools.
With the configuration above, 77 linters are on and they report **69 findings, 18 of them cleared
by `golangci-lint run --fix`**:

| Linter | Findings | What they are |
|---|---:|---|
| modernize | 13 | Newer idioms (`slices.Backward`, `strings.Cut`, `errors.AsType`). All fixed by `--fix`. |
| bodyclose | 11 | All false positives, from three places: 8 at callers of one test helper, 2 at callers of a helper in a command-line tool, and 1 where a type takes ownership of the response. Both helpers close the body and then return the `*http.Response`, which bodyclose can't follow. Suppressed per line — or the helpers return what callers use (status, headers, body) instead of a response whose body is already closed, which clears ten and reads better. |
| forcetypeassert | 8 | Unchecked type assertions in production code, five of them in one code generator. Each either becomes a checked assertion or is suppressed where the type is guaranteed. |
| noctx | 8 | `net.Listen` and `http.NewRequest` without a context, mostly in tests. |
| gochecknoglobals | 4 | Two lookup tables in production code, which are suppressed, and two test globals, which become locals or fixtures. |
| embeddedstructfieldcheck | 3 | Embedded fields not first, or not set apart from the rest. |
| errchkjson | 3 | `json.Marshal` errors discarded, one in production code. |
| errname | 3 | Error types not named `…Error`. One exported type may deserve a suppression; the other two are renames. |
| revive | 3 | Two exported constants without doc comments, and a `time.Duration` whose name ends in a unit. |
| errorlint | 2 | A sentinel compared with `!=`, and a deliberate `%v` that should wrap or say why it doesn't. |
| gosec | 2 | A code generator reads a file path it's given and writes its output `0644` — both intended for a code generator, both suppressed with that reason. |
| unparam | 2 | Test helpers whose parameter always gets the same value. |
| usestdlibvars | 2 | `"200"` for `http.StatusOK`. Fixed by `--fix`. |
| containedctx | 1 | A type holds its request's context — the accepted exception for a value that *is* one request. Suppressed. |
| contextcheck | 1 | Shutdown starts from `context.Background()`; `context.WithoutCancel(ctx)` keeps the request's values and satisfies it. |
| gocritic | 1 | A test slices from `strings.Index` without checking for −1. |
| thelper | 1 | A test helper without `t.Helper()`. |
| unconvert | 1 | A conversion to the type the value already has. |

The other 59 linters that are on found nothing. Some check for bugs this code doesn't have
(`nilerr`, `durationcheck`, `makezero`); some check libraries it uses well (`sloglint`,
`protogetter`); and some, such as `sqlclosecheck`, `testifylint` and `zerologlint`, are for
libraries it doesn't use at all.

For the record, the disabled linters would have reported: wsl 807, nlreturn 202, varnamelen 144,
paralleltest 144, wsl_v5 126, exhaustruct 120, noinlineerr 120, depguard 67 (with no
configuration, it rejects every non-standard import), wrapcheck 59, err113 48, lll 41,
goconst 24, cyclop 20, mnd 20, testpackage 14, prealloc 9, and fewer than 5 each for the rest.

### Style guide

The org style guide lives in `docs/styleguide/`, the name the Google guides it builds on use, in
files the automatic reviewer can be given whole, with nothing else:

- `docs/styleguide/README.md` — what applies in every language, and how review works here.
- `docs/styleguide/go.md` and `docs/styleguide/python.md` — one per language.

`CONTRIBUTING.md` links to it from a short **Code review** section. Each file is short and
cites the external guides rather than restating them. It grows by the existing rule that a point
raised in review more than once gets written down — and shrinks when the calibration report shows
a point has become a linter's job.

**Every language** — readability only:

- Names say what a thing is or does; a reader shouldn't need the implementation to follow a call.
- A function does one thing at one level of abstraction; deep nesting is flattened with early
  returns.
- Comments say why, not what; exported API is documented for its callers.
- No speculative abstraction: an interface, option or layer earns its place with a second user.
- Tests read as specifications: each case says what it checks, and a failure message names the
  input, what came back and what was wanted.
- Nothing a linter or formatter enforces is reported.

**Go** applies the [Google Go Style Guide](https://google.github.io/styleguide/go/) — its
Guide, Decisions and Best Practices, in that order of authority — and
[Go Code Review Comments](https://go.dev/wiki/CodeReviewComments). In particular:

- **Package names and boundaries:** a package is one idea; names don't stutter
  (`storage.Store`, not `storage.StorageClient`); no `util` or `common`.
- **Errors:** wrap with context where the caller gains from it; `%w` makes the wrapped error
  part of the API, so choose it deliberately; handle an error once — don't log it and also
  return it.
- **Interfaces** belong to the consumer, stay small, and aren't declared before a second
  implementation or a test needs one.
- **Goroutines** have an owner and a visible end: whoever starts one makes clear how it stops.
- **Tests** are table-driven where cases vary only by data, report `got` before `want`, use
  `cmp.Diff` for structures, and use no assertion library.

**Python** applies the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html),
except where ruff or `CONTRIBUTING.md` already decides.

### Automatic readability review

A reusable workflow, `.github/workflows/reusable-readability-review.yml`, runs Anthropic's
[`claude-code-action`](https://github.com/anthropics/claude-code-action) with a prompt that
does one job: review this pull request's diff for readability against the style guide, and post
each finding as an inline comment.

- **When:** once per pull request, when it is opened or marked ready for review — after the
  work is ready to read. Drafts are skipped. The workflow also runs on every later push, but
  only to report that the review has happened: its first step asks the GitHub API whether the
  Claude GitHub App has already reviewed this pull request, and if so the job succeeds without
  reviewing again.
- **What it's given:** the diff, and the style guide for the languages the diff touches —
  `docs/styleguide/README.md` plus `go.md` for `.go` files, `python.md` for `.py` files —
  checked out from this repo. The pull request's code is checked out too, so a name or an API
  can be judged in its file and its callers. The review doesn't need the repo's own context but
  may read it: Claude Code Action replaces the root `CLAUDE.md`, `AGENTS.md`, `.claude/` and
  `.mcp.json` with the base branch's, so what it reads has been reviewed, and the pull request
  can't configure its own review.
  Claude gets no shell: its tools are reading files, writing its summary to a file, and posting
  inline comments, and the permission mode denies anything else. The action, the model and the
  permission mode are pinned, so an upstream change of default reaches the review only through
  a Dependabot pull request. A shell command could expand the environment, which holds the model token,
  into a comment that text planted in the pull request asked for.
- **What it's told:** readability only — not correctness, security or design. Nothing a linter
  enforces. Each comment names the style-guide point it applies, in a fixed form the calibration
  report can read, so the author can check the reasoning and the comment teaches as well as
  corrects.
- **Who posts:** the Claude GitHub App posts the findings, and the workflow posts Claude's
  summary as `github-actions[bot]`; both are bots rather than anyone's account, so nobody has
  to approve each comment before it goes out.
- **Which pull requests:** pull requests from a fork, and those opened by Dependabot, are
  skipped — GitHub withholds secrets from fork runs, and the action rejects bot actors.
- **Bounds:** the workflow's own token reads the code and posts the summary —
  `contents: read`, `pull-requests: write` — and `id-token: write` signs in to Google Cloud and
  to the Claude GitHub App, whose token posts the findings. A job timeout, and one review in
  flight per pull request.
- **Credential:** the model token, from `claude setup-token`, lives in Secret Manager in the
  org's devops project in Google Cloud, beside the shared Terraform state; its Terraform is
  in `swimblocks/.github-private`. The workflow signs in over OIDC and reads it, and the identity
  provider admits only this workflow, from this repo's `main`, running in a swimblocks repo: no
  other workflow, in any repo or on any branch, can read the token. The workflow deletes the
  Google credentials file before the review starts.
- **Where to sign in:** the provider's and the secret's resource paths are identifiers, not
  credentials, but they stay out of this public workflow, where they'd point at what to probe.
  They are repo secrets, masked in logs. GitHub Free doesn't give private repos the org's
  secrets, so the settings rollout copies them into every repo from `swimblocks/.github`'s own
  ([`docs/reconciler.md`](../reconciler.md)) — the reconciler's existing reach, rather than a
  copy kept by hand per repo.

There is one copy of the style guide, here; a change to it applies to every repo's next review
with nothing to sync.

A repo opts in with its own thin caller, `.github/workflows/readability-review.yml`, separate
from `ci.yml` because it runs on different events. A reusable workflow can't hold more
permissions than its caller grants, so the caller grants exactly what the review needs:

```yaml
name: Readability review
on:
  pull_request:
    types: [opened, ready_for_review, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write   # the summary comment
  id-token: write        # signing in to Google Cloud and to the Claude GitHub App
jobs:
  review:
    uses: swimblocks/.github/.github/workflows/reusable-readability-review.yml@main
    secrets: inherit
```

#### The review gates the merge

Two rules together make the review blocking:

- **The review must have run.** Its job is a required status check in the org ruleset
  (`settings.yml`). That is why it runs on every push: a required check attaches to the pull
  request's latest commit, so a check that ran only when the pull request opened would be
  missing after the next push and the pull request could never merge. A job skipped for a fork
  or Dependabot counts as passing, as GitHub treats skipped jobs. If the review itself fails —
  the API is down, a usage limit is hit — the check fails and the run is re-run once it can
  succeed; a pull request doesn't merge unreviewed by accident.
- **Every finding must be answered.** The ruleset already requires all review threads to be
  resolved, so each finding is either acted on or replied to and resolved.

The reviewer never approves; whether the change is good is still the human's call.

Requiring the check has an ordering constraint: the ruleset applies to every repo at once, so
every repo must have its `readability-review.yml` caller before the rollout that requires it,
or pull requests in the repos without one block forever.

#### Considered: Anthropic's managed Code Review

Anthropic also runs Code Review as a hosted service, with no workflow file. It reviews for
correctness by default and reads its instructions from each repo's own `REVIEW.md` and
`CLAUDE.md`, including other files only from that same repo's root. A style guide kept here
would have to be copied into every repo and kept in step, which is the drift the reconciler
([0003](0003-settings-releases-and-rollout.md)) exists to prevent for settings. The workflow
route keeps one copy and a focused prompt. Revisit if the hosted service gains a way to read
shared, org-level instructions.

### Calibration report

The lint set and the style guide are starting points, not verdicts. A weekly workflow tunes
them from what the org's repos and pull
requests already record:

- **Lint suppressions.** Every `//nolint:` directive across the org's Go repos, with its linter,
  location and reason. A linter suppressed five or more times is flagged: it is either
  misconfigured for how we write Go, or wrong for us, and the reasons say which.
- **Disabled linters.** Each linter in the disable list is run against every Go repo and its
  findings counted. One whose findings are few and look real is flagged as a candidate to
  switch on, with a sample.
- **Readability findings.** Every finding the readability reviewer posted on a pull request
  merged that week, by the style-guide point it cited, and whether it was **accepted** — the
  lines it commented on changed before merge — or **rejected**, merged unchanged. A point that
  is mostly rejected is flagged for rewording or removal. A point that is mostly accepted and
  mechanical is flagged as a candidate for a linter: switching one on, enabling a `revive` or
  `gocritic` rule, or writing the configuration for one of the linters that needs it — a
  recurring "don't import X" is what `depguard` is for. That is how the org finds out it has a
  use for those.
  The run summary gives the week's findings; a point's case is made from every finding since
  the review began, so it builds up over the weeks rather than starting again each Monday.

**One issue per observation.** Each flag above becomes its own issue, opened the
first week it appears — "bodyclose suppressed 11 times", "go.md *Errors* rejected 4 of 5
times" — with the evidence, labelled `calibration`. Each carries a stable key in a hidden
marker (`lint:bodyclose:suppressed`, `style:go/errors:rejected`), so in later weeks the
workflow finds its own issue instead of opening another. When there is something new — new
suppressions or rejections, with their reasons — it adds a comment saying what changed, and
rewrites the body so it stays a short statement of the case as it now stands: the observation,
the current numbers, the suggested change. History lives in the comments; the body stays
succinct. A week with nothing new touches nothing. Closing the issue is the decision — acting
on it, or deciding not to — and a closed key is never reopened by the workflow; if the case
grows much stronger, it says so on the closed issue once. The full weekly numbers, flagged or
not, go in the workflow run's summary, not in an issue.

The workflow posts as itself, so the issues read as the bot's, not anyone's. It suggests;
it changes nothing. Acting on a suggestion is an ordinary pull request against this design's
`.golangci.yml` or the style guide, linking the issue.

**It runs in private.** The report quotes what it finds — suppression reasons, file paths, code
samples — and most of the org's repos, `fetch-service` among them, are private, while this repo
is public. So the workflow, and the issues, logs and run summaries it produces, live in
`swimblocks/.github-private`: the private counterpart of this repo, named by the GitHub
convention that already makes its `profile/README.md` the org profile only members see. It
becomes the home for org-level work that can't be public, so each new need doesn't bring a new
special-purpose repo. The calibration logic itself stays here, as a tested script under
`scripts/` like the reconciler's, which the private workflow checks out each run: the code is
public, the data isn't.

It reads the org's repos through a GitHub App of its own, `swimblocks-calibrator`, installed on
all repositories with Metadata, Contents and Pull requests read, and Issues write — which it
uses only in `.github-private`. Neither existing app fits:
the reconciler can't read code or pull requests, and [`docs/reconciler.md`](../reconciler.md)
keeps each app to the permissions its one job needs, so the calibrator's grant goes on an
installation of its own rather than widening the reconciler's.

### In the agent work loop

An agent still hands work to the author before any pull request exists (AGENTS.md §3). Before
handing off, it runs `/code-review` on its own diff and fixes what it finds, so the author
isn't reading problems minutes before a reviewer raises them. That local review leaves no
record; it is a courtesy to the author, not the review of record. Once the pull request is open,
answering the readability findings is part of the author's review, and an agent asked to address
them replies in the thread with what changed.

## Rollout

- **Depends on 0005's rollout ([#63](https://github.com/swimblocks/.github/issues/63)):** the
  Go section of `CONTRIBUTING.md` it creates carries this lint set and the suppression rule, not
  the `standard`-only set.
- `docs/styleguide/`, and the **Code review** section in `CONTRIBUTING.md` linking it.
- `AGENTS.md` §3: the pre-handoff `/code-review`, and answering review findings.
- `.github/workflows/reusable-readability-review.yml`.
- The calibration script under `scripts/`, with tests; and `swimblocks/.github-private`,
  created with `scripts/create-repo.sh`, holding the weekly workflow that runs it.
- `swimblocks/.github-private` with the devops project's Terraform: the workload
  identity pool and the token's secret. The operator applies it and adds the token.
- `settings.yml`'s `actions_secrets`, `apply_settings.py` copying them, and the reconciler App's
  Secrets permission.
- Org setup, done once by an org owner: install the
  [Claude GitHub App](https://github.com/apps/claude) on all repositories; approve the
  reconciler's new permission; put the two Google Cloud identifiers on `swimblocks/.github` as
  secrets; create the `swimblocks-calibrator` App, install it on all repositories, and add its
  credentials as secrets of the calibration workflow.
- `scripts/create-repo.sh` prints the `readability-review.yml` caller next to the CI caller.
- Every repo gets its `readability-review.yml` caller; only then does `settings.yml`'s ruleset
  require the review check, in a later settings release.
- **`fetch-service` goes first**, under its own issue: commit the new `.golangci.yml`, fix or
  suppress the 69 findings, add `readability-review.yml`.

## Verification

- **Done:** the lint trial above. The configuration passes `golangci-lint config verify`, and
  the `contextcheck` fix and the `exhaustive` setting were each checked by re-running with them
  applied.
- **Pending, with the workflows:** `actionlint` passes on both. On `fetch-service`'s next pull
  request, the review posts inline comments as the Claude GitHub App, each citing a style-guide
  point; a deliberately planted violation — a stuttering name, say — is reported; and nothing is
  posted about correctness or about what lint enforces. A later push to that pull request
  passes the check without a second review. The first calibration report lists
  `fetch-service`'s suppressions, and the disabled linters' counts above.

## Open items

- **The model credential is still a long-lived token**, the kind of credential
  [0001](0001-github-app-reconciler.md) replaced with GitHub Apps for GitHub access. Keeping it
  in Secret Manager behind OIDC means one copy, readable by one workflow, but it is still
  rotated by hand and tied to the person who made it. Federated model access removes it — Claude
  through Vertex AI in the same devops project, or a Claude Console service account —
  at a per-token cost. Switch once the review has shown its worth; only the workflow's sign-in
  steps change.
- **CI isn't a required check either.** The org ruleset requires no status checks today, so a
  red CI run doesn't block a merge any more than a missing review would. Requiring CI belongs
  with the review check, in the same ruleset change, but is its own decision.
- **Re-review after changes.** A pull request is reviewed once. If substantial rework needs a
  second look, a comment trigger (`@claude review`) may be worth adding; not until it's missed.
- **The Claude GitHub App's permissions** are broader than the review needs, because one app
  serves all of Claude's GitHub features. A custom app limited to contents, issues and pull
  requests would narrow that, at the cost of creating and maintaining one.
- **Accepted versus rejected** is judged from whether the commented lines changed, which misses
  a finding fixed elsewhere and counts an unrelated edit as acceptance. Reading the thread's
  replies, perhaps with Claude, would sharpen it; as would grouping similar suppression reasons.
  Worth adding once there's enough data to be wrong about.
