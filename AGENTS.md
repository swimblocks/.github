# Agent guide — SwimBlocks

This file is the canonical entry point for any AI coding agent (Claude Code, OpenAI Codex,
Cursor, GitHub Copilot, Aider, Gemini CLI, etc.) working on a [SwimBlocks](https://github.com/swimblocks)
repository. It is also a fine "start here" for a human contributor.

The long-form house rules live in [CONTRIBUTING.md](CONTRIBUTING.md). This document is a
distilled, agent-oriented summary plus the bootstrapping a newcomer needs cold.

---

## 1. Project scope

SwimBlocks tools target **Swimming Canada's ecosystem and Canadian provincial associations**.
Some repos are hard-locked to Canadian data sources (e.g. `rems-sync`, `swim-club-tech-survey`);
others are Canada-default but architecturally extensible (e.g. `deck-eval-parser` templates).
**Do not generalise features to other countries unless an issue explicitly asks.**

## 2. Bootstrapping (humans + agents)

If you've just cloned a SwimBlocks repo for the first time:

```bash
# Prereqs (one-time, per machine):
#   Python 3.12+
#   gcloud CLI  (only needed for repos that touch Google Sheets / Drive)
#   gh CLI      (for opening issues / PRs)

cd <repo-root>
python -m venv .venv
.venv/Scripts/activate            # PowerShell: .venv\Scripts\Activate.ps1
                                  # Linux/macOS:  source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q

# If the repo touches Google APIs (rems-sync, etc.):
gcloud auth application-default login
# Share the target Google Sheet with your own Google account.
```

## 3. The work loop (the rule agents most often break)

For **every** change:

1. **Open a GitHub issue first.** Describe the change. This is the unit of work.
2. **Branch** off `main`, named `<issue-number>-<short-slug>`.
3. **Make focused commits.** Coherent, single-purpose. Run `ruff check .` and `pytest -q`
   locally before pushing.
4. **Open a PR** whose description includes `Closes #<issue-number>` and explains the *why*.
5. **Wait for CI green** (lint + tests).
6. **Hand off.** Post a short summary to the human author — what changed, why, lint/test
   results, PR link — then stop. **Agents do not self-merge.** *Exception:* a large mechanical
   change spanning many repos may be agent-merged by prior agreement with the author.
7. The human reviews and squash-merges.

Do not push directly to `main`. Do not use `--no-verify` or otherwise skip hooks. Create new
commits rather than amending already-pushed ones.

## 4. Quality gates (Python repos)

- Lint: `ruff check .` (config in each repo's `pyproject.toml`). Auto-fix with `--fix`.
- Tests: `pytest -q`. Add coverage for new behaviour and regressions.
- CI: each repo's `ci.yml` calls
  [`swimblocks/.github/.github/workflows/reusable-python-ci.yml@main`](.github/workflows/reusable-python-ci.yml).

## 5. Dependencies

- `requirements.txt`: direct runtime + test deps only, UTF-8, `>=` minimums. No full `pip
  freeze` output, no transitive pins.
- `requirements-dev.txt`: layered on top, adds dev-only tools (e.g. `ruff`).
- Dependabot config lives **per repo** at `.github/dependabot.yml` (no org-wide inheritance).

## 6. Secrets, data, and PII

- Never commit `.env`, credentials, or service-account keys (all gitignored).
- Never commit personal data — officials' names/emails, club contact lists, REMS exports.
  Treat such CSV/PDF as local sample data and gitignore it, or scrub before commit.
- Report any exposure privately via the repo's Security tab, not a public issue.

## 7. Creating a new repo

Use [`scripts/create-repo.sh`](scripts/create-repo.sh) — **never** the GitHub UI. It applies
the canonical settings from [`.github/settings.yml`](.github/settings.yml) automatically.
Drift on existing repos is healed by the scheduled
[`reconcile-repo-defaults.yml`](.github/workflows/reconcile-repo-defaults.yml) workflow.

## 8. Other agent-specific files

Each repo carries thin pointer files so any tool finds the right context:

- `CLAUDE.md` -> imports this file (`@AGENTS.md`)
- `.github/copilot-instructions.md` -> "see AGENTS.md"
- `.cursor/rules/main.mdc` -> "see AGENTS.md"

Edit `AGENTS.md`. The pointer files don't need changes.

## 9. When in doubt

- **Don't widen scope.** If an issue says "fix X," fix X. Don't refactor unrelated code.
- **Don't generalise away the Canada specifics.** They are load-bearing.
- **Ask the human** in the issue/PR comments if a requirement is ambiguous, rather than
  guessing.
- For the full rationale of any rule above, read [CONTRIBUTING.md](CONTRIBUTING.md).
