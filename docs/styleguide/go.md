# Go style guide

Go code follows the [Google Go Style Guide](https://google.github.io/styleguide/go/) — its
[Guide](https://google.github.io/styleguide/go/guide),
[Decisions](https://google.github.io/styleguide/go/decisions) and
[Best Practices](https://google.github.io/styleguide/go/best-practices), in that order of
authority — and [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments). Their ID here
is `go/google`.

On top of the [general points](README.md) and the org's golangci-lint set
([CONTRIBUTING.md](../../CONTRIBUTING.md#quality-gates)), these are the points SwimBlocks Go
code is most often held to.

## Packages

A package is one idea, named in one lowercase word that says what it provides. Names don't
stutter: `storage.Store`, not `storage.StorageClient`. No `util`, `common` or `helpers`.

## Errors

Wrap an error with context where the caller gains from it. `%w` makes the wrapped error part of
the function's API, so choose it over `%v` deliberately. Handle an error once: don't log it and
also return it.

## Interfaces

Interfaces belong to the package that uses them, stay small, and aren't declared before a
second implementation or a test needs one.

## Goroutines

Every goroutine has an owner and a visible end: whoever starts one makes clear how it stops.

## Tests

Table-driven where cases vary only by data. Failure messages report `got` before `want`.
Structures are compared with `cmp.Diff`. No assertion library.
