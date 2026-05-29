# .github

Organization-wide defaults for [SwimBlocks](https://github.com/swimblocks).

- [`profile/README.md`](profile/README.md) — the org profile page shown at github.com/swimblocks
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — shared development standards (issue → branch → PR → squash)
- [`SECURITY.md`](SECURITY.md) — how to report vulnerabilities and exposed data
- [`PULL_REQUEST_TEMPLATE.md`](PULL_REQUEST_TEMPLATE.md) — default PR template
- [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE) — bug / feature / chore issue forms
- [`.github/workflows/reusable-python-ci.yml`](.github/workflows/reusable-python-ci.yml) — shared
  Python CI (ruff + pytest), called by each repo's `ci.yml`

GitHub automatically applies the community-health files above to any repo in the org that
doesn't define its own. Reusable workflows are referenced explicitly via
`uses: swimblocks/.github/.github/workflows/reusable-python-ci.yml@main`.

> **Per-repo, not inherited:** Dependabot config (`.github/dependabot.yml`) and branch-protection
> rules are configured per repository — GitHub does not inherit these from the org `.github` repo.
