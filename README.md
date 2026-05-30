# .github

Organization-wide defaults for [SwimBlocks](https://github.com/swimblocks).

- [`profile/README.md`](profile/README.md) — the org profile page shown at github.com/swimblocks
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — shared development standards (issue → branch → PR → squash)
- [`AGENTS.md`](AGENTS.md) — canonical entry point for AI coding agents (Codex, Cursor, Claude Code, …)
- [`SECURITY.md`](SECURITY.md) — how to report vulnerabilities and exposed data
- [`PULL_REQUEST_TEMPLATE.md`](PULL_REQUEST_TEMPLATE.md) — default PR template
- [`CODEOWNERS`](CODEOWNERS) — review requirements for policy-bearing files
- [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE) — bug / feature / chore issue forms
- [`.github/settings.yml`](.github/settings.yml) — declarative org-wide repo settings
- [`.github/workflows/reusable-python-ci.yml`](.github/workflows/reusable-python-ci.yml) — shared
  Python CI (ruff + pytest), called by each repo's `ci.yml`
- [`.github/workflows/reconcile-repo-defaults.yml`](.github/workflows/reconcile-repo-defaults.yml)
  — applies `settings.yml` across the org on schedule / dispatch / new-repo events
- [`scripts/create-repo.sh`](scripts/create-repo.sh) — **the** way to create a new SwimBlocks
  repo (defaults to private; aligns settings immediately)
- [`scripts/make-public.sh`](scripts/make-public.sh) — **the** way to promote a private repo
  to public (runs pre-public checks: secret scans of tree + history, required-files audit,
  then flips visibility and applies branch protection). This is the documented home for any
  pre-public step we learn we need.
- [`scripts/apply-settings.py`](scripts/apply-settings.py) — applies `settings.yml` to a given
  repo; used by the reconciler workflow, `create-repo.sh`, and `make-public.sh`

GitHub automatically applies the community-health files above to any repo in the org that
doesn't define its own. Reusable workflows are referenced explicitly via
`uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main`.

See [CONTRIBUTING.md → Repo settings (org-wide policy)](CONTRIBUTING.md#repo-settings-org-wide-policy)
for the policy table and enforcement details.

> **Per-repo, not inherited:** Dependabot config (`.github/dependabot.yml`) and branch-protection
> rules are configured per repository — GitHub does not inherit these from the org `.github` repo.
