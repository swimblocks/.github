# SwimBlocks

Open tooling for **Canadian swimming** — built around Swimming Canada's REMS / SportLomo
ecosystem and provincial associations. The tools lean on Canada-specific data sources and
workflows; they are not yet designed to work against other countries' data, though we may
consider supporting that in the future.

## Repositories

| Repo | What it does |
|---|---|
| [deck-eval-gen](https://github.com/swimblocks/deck-eval-gen) | Generates printable deck-evaluation PDF forms from an officials grid. |
| [deck-eval-parser](https://github.com/swimblocks/deck-eval-parser) | Parses on-deck evaluation PDFs (fillable or scanned) into structured data via provincial templates + a local vision model. Currently focused on Canadian forms. |
| [rems-sync](https://github.com/swimblocks/rems-sync) | Bi-directional sync between Swimming Canada's REMS/SportLomo registry and your club's systems (Google Sheets); uploads deck evaluations to REMS. |
| [swim-club-tech-survey](https://github.com/swimblocks/swim-club-tech-survey) | Fully automated monthly crawl detecting which team-management / registration platforms swim clubs use. Currently Canadian clubs, extensible elsewhere. |

## How we work

Every repo follows the shared standards in
[CONTRIBUTING.md](https://github.com/swimblocks/.github/blob/main/CONTRIBUTING.md):
one issue → one branch → one PR that closes it → squash-merge once CI is green.

Built with assistance from [Claude](https://claude.ai) by Anthropic.
