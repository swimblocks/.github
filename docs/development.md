# Development

This doc covers everything *not* in the repos themselves: how to lay out your local clones, how
to install a thin layer of user-local agent guidance, and how to keep that layer aligned with
the canonical files in [`swimblocks/.github`](https://github.com/swimblocks/.github). If you've
just cloned a SwimBlocks repo for the first time, the repo's own README + this page are the two
things to read.

## TL;DR

```bash
# 1. Make sure ghq is configured to root at ~/src (one-time).
git config --global ghq.root "$HOME/src"

# 2. Clone the standards repo first.
ghq get https://github.com/swimblocks/.github

# 3. From any new shell, install the user-local agent files.
bash ~/src/github.com/swimblocks/.github/scripts/install-local-agent-files.sh

# 4. Clone whatever working repos you need.
ghq get https://github.com/swimblocks/rems-sync
ghq get https://github.com/swimblocks/deck-eval-parser
ghq get https://github.com/swimblocks/swim-club-tech-survey
```

That's the happy path. The sections below explain *why* each piece exists.

## Why a "local" layer at all

Each working repo has its own [`AGENTS.md`](../AGENTS.md) plus pointer files for Claude /
Copilot / Cursor (see issues
[#73](https://github.com/swimblocks/rems-sync/issues/73),
[#51](https://github.com/swimblocks/deck-eval-parser/issues/51),
[#22](https://github.com/swimblocks/swim-club-tech-survey/issues/22)).
That covers any agent invoked **inside** the repo.

But a meaningful share of cross-repo work runs with the agent's cwd **above** a repo — a
batch migration across all SwimBlocks repos, an audit, "open an issue on whichever repo
owns X." For those, the agent inherits whatever lives in parent-directory files. Claude
Code walks `<cwd>` → parents → `~/.claude/` looking for `CLAUDE.md`; other agents that
respect `AGENTS.md` follow similar rules.

The user-local files give those out-of-repo invocations the same context an in-repo
invocation would have, without duplicating the canonical text.

## Recommended layout (ghq)

[`ghq`](https://github.com/x-motemen/ghq) is a small Go binary that clones every Git repo
into a canonical path derived from its URL. With `ghq.root = ~/src`, the layout becomes:

```
~/src/
├── AGENTS.md                              # installed (cross-everything)
└── github.com/
    └── swimblocks/
        ├── AGENTS.md                      # installed (org scope)
        ├── CLAUDE.md                      # installed (Claude Code @import)
        ├── .github/                       # the standards repo
        │   ├── AGENTS.md                  # CANONICAL — single source of truth
        │   ├── CONTRIBUTING.md
        │   └── …
        ├── rems-sync/                     # each working repo
        │   ├── AGENTS.md                  # per-repo, points at the org one
        │   ├── CLAUDE.md
        │   └── .github/copilot-instructions.md
        ├── deck-eval-parser/
        └── swim-club-tech-survey/
```

Why ghq specifically:

- Predictable paths — every agent and every script can assume the layout.
- `ghq list`, `ghq get`, `ghq look` make cross-repo navigation trivial.
- It's the layout the install script and the SwimBlocks tooling assume.

If you'd rather not use ghq, replicate the same `github.com/<org>/<repo>` shape manually;
nothing here is ghq-specific *except* the convenience of `ghq get <url>` doing the right thing.

## What the install script writes

[`scripts/install-local-agent-files.sh`](../scripts/install-local-agent-files.sh) writes three
small files. Each is a pointer; none duplicates the canonical content.

| Path | Role |
|---|---|
| `~/src/AGENTS.md` | Cross-everything. Tells any agent invoked under `~/src` that SwimBlocks-scoped work is governed by the standards in `~/src/github.com/swimblocks/.github/AGENTS.md`. Non-SwimBlocks work is the agent's own problem. |
| `~/src/github.com/swimblocks/AGENTS.md` | Org-scope pointer. One-line redirect to the canonical `.github/AGENTS.md` next door. Any agent running at the SwimBlocks org level picks up the canonical rules without an in-repo cwd. |
| `~/src/github.com/swimblocks/CLAUDE.md` | Claude Code import. Uses `@./.github/AGENTS.md` so Claude Code (which natively reads `CLAUDE.md`) gets the same content other agents read from `AGENTS.md`. |

The canonical content (`~/src/github.com/swimblocks/.github/AGENTS.md`) is just the cloned
standards repo. The install script doesn't touch that file; updates flow in via
`git pull` like any other repo.

The script is **idempotent and refuses to overwrite** existing files unless you pass `--force`.
A `--dry-run` flag prints what it would do without writing.

## Manual install (if you don't trust the script)

The three pointer files are short enough to write by hand. See the script's comments for the
exact content, or read [`scripts/install-local-agent-files.sh`](../scripts/install-local-agent-files.sh)
top-to-bottom — it's documented inline.

## Maintenance

Keep the standards repo up to date:

```bash
cd ~/src/github.com/swimblocks/.github && git pull
```

That's it. The pointer files never need updating; they always read the latest
`.github/AGENTS.md` from your local clone.

If the install script itself changes (new pointer files, new layout), re-run it. It will
report which files it leaves alone and which it would update; with `--force` it overwrites.

## What about other agents?

| Agent | What it reads | Where it picks up SwimBlocks rules |
|---|---|---|
| Claude Code | `CLAUDE.md` (hierarchical: cwd → parents → `~/.claude/`); supports `@<path>` imports | Per-repo `CLAUDE.md` (in-repo); user-local `~/src/github.com/swimblocks/CLAUDE.md` (parent-walk) |
| OpenAI Codex / Codex CLI | `AGENTS.md` (cwd, sometimes parents) | Per-repo `AGENTS.md`; user-local parent-dir `AGENTS.md` |
| Cursor | `.cursor/rules/*.mdc` and `AGENTS.md` | Per-repo `.cursor/rules/main.mdc` + `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | Per-repo `.github/copilot-instructions.md` |
| Aider | `CONVENTIONS.md` (configurable) | Repos can drop this in if you use Aider; not part of the default rollout |
| Gemini CLI | `GEMINI.md`, `AGENTS.md` (emerging) | Per-repo `AGENTS.md` |

The takeaway: `AGENTS.md` is the closest to a lingua franca. The user-local layer is *mostly*
for Claude Code's parent-walk advantage; in-repo agents already see the per-repo files.

## Prerequisites checklist

Standard SwimBlocks dev box:

- **Python 3.12+** (every working repo uses it).
- **`gh` CLI**, logged in (`gh auth status` shows green).
- **`gcloud` CLI**, logged in via `gcloud auth application-default login` (only needed for
  repos that touch Google Sheets / Drive — `rems-sync`, `swim-club-tech-survey`).
- **`ghq`** (optional but recommended for the layout above).
- **`ruff`** and **`pytest`** are installed per-repo via each repo's `requirements-dev.txt`.

See each repo's own README for repo-specific setup beyond this.

## Out of scope for this doc

- Per-repo agent files (rolled out under their own issues).
- The standards repo's own contents (read [`AGENTS.md`](../AGENTS.md) and
  [`CONTRIBUTING.md`](../CONTRIBUTING.md) for those).
- Setting up new SwimBlocks repos (use [`scripts/create-repo.sh`](../scripts/create-repo.sh)).
