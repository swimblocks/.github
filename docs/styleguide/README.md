# SwimBlocks style guide

How SwimBlocks code is written so that it reads well. These points apply in every language;
each language adds its own:

- [Go](go.md)
- [Python](python.md)

**Lint is part of the style.** Code passes the org lint set for its language
([CONTRIBUTING.md](../../CONTRIBUTING.md#quality-gates)), and what a linter checks isn't
repeated here. This guide covers what takes judgement.

Each point has an ID made of its file and heading — `general/names`, `go/errors` — so a review
comment can say which point it applies.

## Names

Names say what a thing is or does. A reader shouldn't need the implementation to follow a call.

## Functions

A function does one thing at one level of abstraction. Deep nesting is flattened with early
returns.

## Comments

A comment explains what the code can't say for itself: why it is this way, not what it does.
Exported API carries doc comments written for its callers — what it does, and what they need to
know to use it. A TODO links the issue that will resolve it
([CONTRIBUTING.md](../../CONTRIBUTING.md#code-comments)).

## Abstraction

No speculative abstraction: an interface, option or layer earns its place with a second user.

## Tests

Tests read as specifications: each case says what it checks, and a failure message names the
input, what came back and what was wanted.

## Changing this guide

A point raised in review more than once gets written down here. A point that review keeps
rejecting gets reworded or removed; one that is mechanical enough for a linter becomes the
linter's job and leaves this guide. Either way, it's an ordinary issue and pull request against
this directory. The planned calibration report
([design 0007](../design/0007-review-standard.md#calibration-report)) will supply the evidence.
