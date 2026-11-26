# Readability review

Living reference for the automatic readability review:
[`reusable-readability-review.yml`](../.github/workflows/reusable-readability-review.yml) and the
caller each repo runs it from. Keep this doc current as they change; the decision history is
[design 0007](design/0007-review-standard.md). How authors answer a review is in
[CONTRIBUTING.md → Code review](../CONTRIBUTING.md#code-review).

## What it does

Claude reviews each pull request once, against the [org style guide](styleguide/README.md) for
what the pull request changes, and posts each finding as an inline comment from the Claude
GitHub App. Every finding names the point it applies, such as `[go/errors]`. When it's done,
the workflow posts a summary comment saying how many findings there were.

The workflow runs on every push, so its check is on the latest commit, but after the first
review it finds the summary comment and passes without reviewing again. A pull request whose
changes the style guide doesn't cover passes without a review. Drafts, pull requests from forks
and pull requests opened or pushed by bots (Dependabot) are skipped.

In public repos, the ruleset in [`settings.yml`](../.github/settings.yml) makes the check,
`review / review`, required, and already requires every review thread to be resolved, so a
pull request merges only once it has been reviewed and every finding answered. A skipped check
counts as passed. Private repos get no ruleset on GitHub Free, so there the review advises but
doesn't block.

## What it needs

| Where | What | Kept in place by |
|---|---|---|
| Each repo | `.github/workflows/readability-review.yml`, a copy of [`workflow-templates/readability-review.yml`](../workflow-templates/readability-review.yml) | [`create-repo.sh`](../scripts/create-repo.sh) commits it to a new repo; the rollout fails a repo without it, or with a changed copy (`required_files` in [`settings.yml`](../.github/settings.yml)) |
| Each repo | The Claude GitHub App, installed | By hand, on all repositories |
| Each repo | Secrets `SWIMBLOCKS_CI_WIF_PROVIDER` and `SWIMBLOCKS_CI_REVIEW_SECRET`: where to sign in to Google Cloud, and which secret holds the model token | The rollout copies them from this repo ([reconciler](reconciler.md)) |
| The org's devops Google Cloud project | A workload identity provider that admits only this workflow, from this repo's `main`, run in a SwimBlocks repo; and the secret `claude-code-oauth-token`, which that identity alone may read | Terraform in `swimblocks/.github-private`'s `terraform/`, applied by the operator. The secret's value is added by hand and never enters Terraform state. |

The model token is a Claude Code OAuth token. To replace it, the operator runs
`claude setup-token` and adds the result as a new version:
`gcloud secrets versions add claude-code-oauth-token --project=<project> --data-file=-`. The
next review reads the latest version.

## Isolation

A pull request is code under review, not instructions, and the review runs with a model token
the pull request must not be able to reach. The workflow's comments give the detail. In short:

- Claude gets no shell. It can read files, write its summary, and post inline comments.
- Reads stop at the checkout, and `/proc` and the runner's temporary files are denied.
- The style guide and the repository's `.git` are moved out of the checkout before Claude
  starts. The action writes its own token into `.git/config`.
- The root's Claude config (`CLAUDE.md`, `AGENTS.md`, `.claude/` and the like) is replaced with
  the base branch's by the action. Deeper copies, symbolic links and a `.readability-review/`
  of the pull request's own are deleted first.
- The Google Cloud credentials file is deleted once the token is read.
- Every action is pinned to a commit, since every step can mint the job's sign-in token.
  Dependabot proposes each new release as a pull request.

## Operating it

**Adding it to an existing repo.** Open a pull request adding a copy of the template, and
nothing else. It changes nothing the style guide covers, so it passes without a review. A pull
request that adds the caller alongside other changes gets a failing review check instead:
Claude Code Action runs only once the caller is on the default branch (see Troubleshooting).

**Re-running.** **Re-run all jobs** (`gh run rerun <run>`) uses the reusable workflow as it is
on `main` now. **Re-run failed jobs**, or a single job (`gh run rerun --failed`), uses it as it
was when the run first started, so it won't pick up a fix to the reusable workflow.

**Reviewing a pull request again.** The summary comment is what marks a pull request reviewed.
Delete it, and the next push reviews the pull request again, as it then stands.

**Changing the style guide.** The review reads the style guide from this repo's `main` at the
start of each run, so a merged change applies to the next review in every repo.

**Calibration.** A weekly report in `swimblocks/.github-private` reads lint suppressions and how
review findings were answered, and suggests changes to the lint set and the style guide
(`docs/calibrator.md` there).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The Review step warns `Workflow validation failed. The workflow file must exist and have identical content to the version on the repository's default branch`, then the run fails with `The review didn't write its summary` | The pull request adds or changes the caller, and also changes what the style guide covers; Claude Code Action won't run until the caller is on the default branch | Put the caller change in a pull request of its own, merge it, then push to this one |
| A pull request can't merge: `review / review` is `Expected — Waiting for status to be reported` | No review ran on the latest commit: the repo has no caller, or the run hasn't started | Check the repo has the caller (the rollout reports it), and that Actions ran on that push |
| A re-run fails the same way after the reusable workflow was fixed | Re-running failed jobs uses the reusable workflow as it was when the run started | Re-run all jobs instead |
| `SWIMBLOCKS_CI_REVIEW_SECRET isn't projects/<project>/secrets/<name>` | The secret holds something else | Set it on this repo from `terraform output -raw readability_review_secret`, then run the rollout |
| Read the model token fails: `the caller does not have permission` | Something on the Google side refused the review's identity | Turn on data access audit logging in the devops Google Cloud project and re-run; the logs should show what refused it. Turn it off afterwards: Terraform owns the project's IAM policy. |
| Read the model token fails: `rejected by the attribute condition` | The sign-in came from somewhere the provider doesn't admit: not this workflow, or not from `main` | Run the review from `main`; a branch of the reusable workflow can't sign in |
| The rollout reports `FAIL file '.github/workflows/readability-review.yml': could not read: ... (HTTP 404)` | The repo has no caller | A pull request adding it |
| The same, with `(HTTP 403)` | The reconciler lacks Contents read | Grant it ([reconciler](reconciler.md)) |
| The rollout reports `differs from workflow-templates/readability-review.yml` | The repo's caller was edited | A pull request restoring the template's copy, or a change to the template if every repo should have it |
