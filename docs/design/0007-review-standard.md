# 0007 — Automatic code review and a stricter Go lint set

Status: proposed

Tracking issue: [#68](https://github.com/swimblocks/.github/issues/68).

## Context

[0005](0005-go-standard.md) admits Go as an org language, with golangci-lint's `standard`
set as its lint baseline. That set catches bugs — unchecked errors, vet findings, dead code —
but says almost nothing about readability, and `swimblocks/fetch-service` is about to bring
the org its first substantial Go code. Nobody in the org has had their Go reviewed for
readability before, so the bar has to be written down rather than carried in someone's head.

Review today is whatever the maintainer and their agent notice. There is no written rubric
for any language: `CONTRIBUTING.md` holds the house rules and folds in rules learned from
review, but nothing says what a reviewer looks for beyond them. Nothing reviews a pull request
unless someone remembers to ask for one, and a review run in a local session leaves nothing on
the pull request.

Three layers, each doing what the others can't:

- **Linters** check what is mechanical, on every push, for free.
- **A written rubric** says what a reviewer checks beyond the linters — the judgment calls.
- **An automatic reviewer** applies the rubric to every pull request without anyone
  remembering to ask, and leaves its findings on the pull request where they stay.

## Design

### Go lint set

The org `.golangci.yml` becomes:

```yaml
version: "2"
linters:
  default: standard        # errcheck, govet, ineffassign, staticcheck, unused
  enable:
    - errorlint            # errors.Is/As, and %w when wrapping
    - gocritic             # style and likely-mistake checks
    - misspell
    - modernize            # newer idioms: min/max, slices, strings.Cut, errors.AsType
    - noctx                # requests and listeners carry a context
    - nolintlint           # //nolint names its linter and is still needed
    - revive               # golint's successor: doc comments, naming, receivers
    - unparam              # parameters that always get the same value
    - usestdlibvars        # http.StatusOK, not 200
  settings:
    revive:
      enable-default-rules: true
      rules:
        - name: unused-parameter
          disabled: true
formatters:
  enable: [gofmt, goimports]
```

As in 0005, the set is an org decision: a repo commits this file unchanged, and an addition
or removal is a change to the org standard.

#### Trial against `fetch-service`

Before choosing, the candidate set was run against `fetch-service` at `373d1ce` (the
`6-storage` branch, about twenty test files and seven internal packages):

| Linter | Findings | Verdict |
|---|---:|---|
| revive | 34 | 31 are `unused-parameter`, on `http.HandlerFunc`s and test handlers whose signatures are fixed. Rule disabled. The other 3 are real: two exported constants without doc comments, and a `time.Duration` named `RetryMin`. |
| modernize | 13 | All real and all fixed by `golangci-lint run --fix`. |
| bodyclose | 11 | All false positives. Every body is closed, but in a helper or by the type that takes ownership of the response — the normal shape in an HTTP fetcher, and one bodyclose can't follow. **Dropped.** |
| noctx | 8 | Real: `net.Listen` and `http.NewRequest` without a context, mostly in tests. |
| errorlint | 2 | Real: an `!=` comparison against a sentinel error in a test, and a deliberate `%v` that should either wrap or say why it doesn't. |
| unparam | 2 | Real, both in tests. |
| usestdlibvars | 2 | Real, fixed by `--fix`. |
| gocritic | 1 | Real: a test slices from `strings.Index` without checking for −1. |
| contextcheck | 1 | False positive: the server's shutdown deliberately starts from a fresh context after the serving one is cancelled. **Dropped.** |

With `bodyclose`, `contextcheck` and `unused-parameter` gone, 31 findings remain, all
genuine; `--fix` clears 17 of them, leaving 14 to fix by hand. None was a bug in production
code. That is the right calibration: a set that is quiet when the code is good, so a finding is
worth reading.

### Review rubric

`CONTRIBUTING.md` gains a **Code review** section: what a reviewer, human or automatic, checks
beyond lint. It is short, cites the external guides rather than restating them, and grows by
the existing rule that a point raised in review more than once gets folded into the house rules.

**Every language:**

- The change does what its issue says, and no more ([AGENTS.md §10](../../AGENTS.md)).
- Names say what a thing is or does; a reader shouldn't need the implementation to follow a call.
- Tests check behaviour, not implementation, and a bug fix comes with a test that would have
  caught it.
- Comments say why, not what; a TODO links an issue ([Code comments](../../CONTRIBUTING.md#code-comments)).
- No speculative abstraction: an interface, option or layer earns its place with a second user.
- Nothing CI already enforces is reported — lint, formatting, type errors, failing tests.

**Go** reviews apply the [Google Go Style Guide](https://google.github.io/styleguide/go/) — its
Guide, Decisions and Best Practices, in that order of authority — and
[Go Code Review Comments](https://go.dev/wiki/CodeReviewComments). In particular:

- **Package names and boundaries:** a package is one idea; names don't stutter
  (`storage.Store`, not `storage.StorageClient`); no `util` or `common`.
- **Errors:** wrap with context where the caller gains from it; choose `%w` or `%v` deliberately,
  since `%w` makes the wrapped error part of the API; handle an error once — don't log it and
  also return it.
- **Interfaces** belong to the consumer, stay small, and aren't declared before a second
  implementation or a test needs one.
- **Context** is the first parameter and isn't stored in a struct.
- **Goroutines** have an owner and a visible end: whoever starts one makes clear how it stops.
- **Tests** are table-driven where cases vary only by data, report `got` before `want`, use
  `cmp.Diff` for structures, and use no assertion library.

**Python** reviews apply the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html), except where
ruff or `CONTRIBUTING.md` already decides.

### Automatic PR review

A reusable workflow, `.github/workflows/reusable-claude-review.yml`, runs Anthropic's
[`claude-code-action`](https://github.com/anthropics/claude-code-action) with the official
`code-review` plugin and posts its findings as inline comments on the pull request.

- **When:** when a pull request is opened or marked ready for review — once per pull request,
  after the work is ready to read. Drafts are skipped; a later push doesn't start another.
- **Against what:** the workflow also checks out `swimblocks/.github` and puts its
  `CONTRIBUTING.md` and `AGENTS.md` where Claude Code reads user-level instructions
  (`~/.claude/CLAUDE.md` on the runner). The review then sees the house rules and the rubric as
  instructions, alongside the repo's own `CLAUDE.md`. There is one copy of the rubric, in this
  repo; a change to it applies to every repo's next review with nothing to sync.
- **Who posts:** the Claude GitHub App, so findings come from a bot rather than from anyone's
  account, and nobody has to approve each comment before it goes out.
- **Which pull requests:** pull requests from a fork, and those opened by Dependabot, are
  skipped — GitHub withholds secrets from fork runs, and the action rejects bot actors.
- **Cost and safety:** read-only repository permissions, a job timeout, and one review in
  flight per pull request.
- **Credential:** an org-level Actions secret. The workflow accepts either an API key
  (`ANTHROPIC_API_KEY`) or a token from `claude setup-token` (`CLAUDE_CODE_OAUTH_TOKEN`), so the
  credential can change without changing any repo.

A repo opts in with its own thin caller, `.github/workflows/review.yml`, separate from
`ci.yml` because it runs on different events:

```yaml
name: Review
on:
  pull_request:
    types: [opened, ready_for_review]
jobs:
  review:
    uses: swimblocks/.github/.github/workflows/reusable-claude-review.yml@main
    secrets: inherit
```

The review is advisory. It is not a required status check, and it never approves or blocks.

#### What the record does and doesn't guarantee

The comments stay on the pull request after merge, which is the record. The ruleset's
"all threads resolved" rule would make every finding get an answer before merge, but the
[solo-admin merge path](../../CONTRIBUTING.md#solo-admin-merge-path) merges with an admin
bypass, which skips that rule too. Until a second code owner exists, answering each finding is
a habit rather than a gate: reply to say what changed, or why not, and resolve the thread.

#### Considered: Anthropic's managed Code Review

Anthropic also runs Code Review as a hosted service: no workflow file, several reviewing agents
with a verification step, and a check run on each pull request. It reads review instructions
from each repo's own `REVIEW.md` and `CLAUDE.md`, and can include other files only from that
same repo's root. An org rubric kept here would have to be copied into every repo and kept in
step, which is the drift the reconciler ([0003](0003-settings-releases-and-rollout.md)) exists
to prevent for settings. The workflow route keeps one copy. Revisit if the hosted service gains
a way to read shared, org-level instructions.

### In the agent work loop

An agent still hands work to the author before any pull request exists (AGENTS.md §3). Before
handing off, it runs `/code-review` on its own diff and fixes what it finds, so the author
isn't reading problems the bot will raise minutes after the pull request opens. That local
review leaves no record; it is a courtesy to the author, not the review of record. Once the
pull request is open, answering the bot's findings is part of the author's review, and an
agent asked to address them replies in the thread with what changed.

## Rollout

- **Depends on 0005's rollout ([#63](https://github.com/swimblocks/.github/issues/63)):** the
  Go section of `CONTRIBUTING.md` it creates carries this lint set, not the `standard`-only one.
- `CONTRIBUTING.md`: the **Code review** section above.
- `AGENTS.md` §3: the pre-handoff `/code-review`, and answering review findings.
- `.github/workflows/reusable-claude-review.yml`.
- Org setup, done once by an org owner: install the
  [Claude GitHub App](https://github.com/apps/claude) on all repositories, and add the
  credential as an org Actions secret.
- `scripts/create-repo.sh` prints the `review.yml` caller next to the CI caller.
- **`fetch-service` goes first**, under its own issue: commit the new `.golangci.yml`, fix the
  31 findings, add `review.yml`.

## Verification

- **Done:** the lint trial above, with golangci-lint 2.15.0 on Go 1.27.4; the final set passes
  `golangci-lint config verify`.
- **Pending, with the workflow:** `actionlint` passes on `reusable-claude-review.yml`. On
  `fetch-service`'s next pull request, the review runs and posts inline comments as the Claude
  GitHub App, and a deliberately planted rubric violation — a stuttering name, say — is reported,
  which shows the rubric reached the review. If it isn't, the workflow passes the rubric with
  `--append-system-prompt` instead.

## Open items

- **Re-review after changes.** A pull request is reviewed once. If substantial rework needs a
  second look, a comment trigger (`@claude review`) may be worth adding; not until it's missed.
- **The Claude GitHub App's permissions** are broader than the review needs, because one app
  serves all of Claude's GitHub features. A custom app limited to contents, issues and pull
  requests would narrow that, at the cost of creating and maintaining one. Revisit if the app is
  ever used for anything beyond review.
