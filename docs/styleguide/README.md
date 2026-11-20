# SwimBlocks style guide

What a reviewer checks beyond lint, for readability, whether the reviewer is a person or the
automatic readability review of [design 0007](../design/0007-review-standard.md). Each file
stands alone, so a reviewer can be given this one and the file for each language a pull request
touches, and nothing else.

- [Go](go.md)
- [Python](python.md)

Readability only. Correctness, security and design are reviewed elsewhere: CI, the author's
own review before handing off, and the human reviewer.

## Points

Each point has an ID, the heading's anchor: `general/names`, `go/errors`. A review comment
starts with the ID of the point it applies, in square brackets — `[go/errors]` — so the author
can check the reasoning, and the weekly calibration report can count which points are accepted
and which are rejected.

### lint

Nothing a linter or formatter enforces is reported. CI already says it, and saying it twice
spends the reader's attention on what a machine has covered.

### names

Names say what a thing is or does. A reader shouldn't need the implementation to follow a call.

### functions

A function does one thing at one level of abstraction. Deep nesting is flattened with early
returns.

### comments

Comments say why, not what. Exported API is documented for its callers. A TODO links an issue
([CONTRIBUTING.md](../../CONTRIBUTING.md#code-comments)).

### abstraction

No speculative abstraction: an interface, option or layer earns its place with a second user.

### tests

Tests read as specifications: each case says what it checks, and a failure message names the
input, what came back and what was wanted.

## Changing this guide

A point raised in review more than once gets written down here. A point the calibration report
shows is mostly rejected gets reworded or removed; one that is mostly accepted and mechanical
becomes a linter's job and leaves this guide. Either way, it's an ordinary issue and pull
request against this directory.
