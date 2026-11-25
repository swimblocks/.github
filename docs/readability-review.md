# Readability review

Living reference for the automatic readability review:
[`reusable-readability-review.yml`](../.github/workflows/reusable-readability-review.yml) and the
caller each repo runs it from. Keep this doc current as they change; the decision history is
[design 0007](design/0007-review-standard.md). How authors answer a review is in
[CONTRIBUTING.md → Code review](../CONTRIBUTING.md#code-review).

## What it does

Claude reviews each pull request once, against the [org style guide](styleguide/README.md) for
the languages the pull request changes (today Go and Python), and posts each finding as an
inline comment from the Claude GitHub App. Every finding names the point it applies, such as
`[go/errors]`. When it's done, the workflow posts a summary comment saying how many findings
there were.

The workflow runs on every push, so its check is on the latest commit, but after the first
review it finds the summary comment and passes without reviewing again. A pull request that
changes no Go or Python passes without a review. Drafts, pull requests from forks and pull
requests opened or pushed by bots (Dependabot) are skipped.

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

## What keeps the review to the change

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

**Adding it to an existing repo.** Open a pull request adding a copy of the template. That
pull request's own review check fails: Claude Code Action runs only once the caller is on the
default branch (see Troubleshooting). Merge it anyway; the next pull request is reviewed.

**Re-running.** A re-run uses the version of the reusable workflow its run first started with,
not the current `main`. To pick up a change to the reusable workflow, push a new commit to the
pull request instead: an empty one works (`git commit --allow-empty`).

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
| The Review step warns `Workflow validation failed. The workflow file must exist and have identical content to the version on the repository's default branch`, then the run fails with `The review didn't write its summary` | The pull request adds or changes the caller, which Claude Code Action won't run until it is on the default branch | Expected on that pull request. Merge it; the next one is reviewed. |
| A re-run fails the same way after the reusable workflow was fixed | Re-runs use the reusable workflow as it was when the run started | Push a commit (an empty one works) |
| `SWIMBLOCKS_CI_REVIEW_SECRET isn't projects/<project>/secrets/<name>` | The secret holds something else | Set it on this repo from `terraform output -raw readability_review_secret`, then run the rollout |
| Read the model token fails: `the caller does not have permission` | Something on the Google side refused the review's identity. It once was Cloud Resource Manager, asked for the project because the sign-in had none; the "Which project the token is in" step now supplies it. | Find the refusal in the audit logs (below) |
| Read the model token fails: `rejected by the attribute condition` | The sign-in came from somewhere the provider doesn't admit: not this workflow, or not from `main` | Run the review from `main`; a branch of the reusable workflow can't sign in |
| The rollout reports `FAIL file '.github/workflows/readability-review.yml': could not read: ... (HTTP 404)` | The repo has no caller | A pull request adding it |
| The same, with `(HTTP 403)` | The reconciler lacks Contents read | Grant it ([reconciler](reconciler.md)) |
| The rollout reports `differs from workflow-templates/readability-review.yml` | The repo's caller was edited | A pull request restoring the template's copy, or a change to the template if every repo should have it |

**Finding a Google Cloud refusal.** The devops project keeps no data access logs, so a refused
request leaves no record by default. To see one, the operator turns them on for IAM and STS,
re-runs the failing job, reads the log, and turns them off again:

1. `gcloud projects get-iam-policy <project> --format=json > policy.json`, add
   `"auditConfigs"` for `iam.googleapis.com` and `sts.googleapis.com` with `ADMIN_READ`,
   `DATA_READ` and `DATA_WRITE`, and `gcloud projects set-iam-policy <project> policy.json`.
   Changes can take a few minutes to apply.
2. Re-run the job, then read the entries:
   `gcloud logging read 'protoPayload.serviceName="sts.googleapis.com" OR protoPayload.serviceName="iam.googleapis.com"' --project=<project> --freshness=1h`.
   A token exchange with an empty `status` succeeded, so the refusal came after it.
3. Set `"auditConfigs": []` and apply the policy again. Terraform owns the project's IAM policy,
   so the setting would otherwise show up in the next plan.
