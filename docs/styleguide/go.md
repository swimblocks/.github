# Go style guide

Go code follows the [Google Go Style Guide](https://google.github.io/styleguide/go/) — its
[Guide](https://google.github.io/styleguide/go/guide),
[Decisions](https://google.github.io/styleguide/go/decisions) and
[Best Practices](https://google.github.io/styleguide/go/best-practices), in that order of
authority — and [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments). Their ID here
is `go/google`.

The org's golangci-lint set ([CONTRIBUTING.md](../../CONTRIBUTING.md#quality-gates)) enforces
the parts of these guides a machine can check. Beyond the [general points](README.md), these are
the ones that take judgement and that SwimBlocks Go code is most often held to.

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

## Lint findings

Most findings have one fix, and `golangci-lint run --fix` applies many of them. These are the
ones where the fix takes judgement, or where suppressing is sometimes right. A suppression names
its linter and says why the finding doesn't apply here, in terms a reader can check:
`//nolint:forcetypeassert // the flight's function returns only *Rules`. Rename with gopls
(your editor's rename, or `gopls rename`), not text search.

- **bodyclose:** close a response where it's received, `defer resp.Body.Close()` after the
  error check. A helper that reads a body returns what callers use (status, headers, the bytes),
  not an `*http.Response` whose body it has already closed, which neither the linter nor a
  reader can follow. Suppress only where a type takes ownership of the response and closes it
  later.
- **forcetypeassert:** use `v, ok := x.(T)` and handle `!ok`. Where the code guarantees the type
  (an `ed25519.PrivateKey`'s `Public()`, a `singleflight` function that returns one type), make
  the assertion in one place and suppress it with that guarantee. Tests are exempt.
- **noctx, contextcheck:** pass the context there is: `http.NewRequestWithContext`,
  `net.ListenConfig`, `t.Context()` in tests. Work that must outlive a cancelled context, such as
  a graceful shutdown, starts from `context.WithoutCancel(ctx)`, not `context.Background()`.
- **containedctx:** pass a context as the first parameter. A struct may hold one only when the
  struct is a single request or call; suppress there and say so.
- **gochecknoglobals:** state becomes a field or a local, and a test global a local or a
  fixture. Parse a template where it's used. A fixed lookup table, built once and never written,
  may stay, suppressed with that reason.
- **errname:** rename the type to end in `Error`. An exported type that callers use as a value
  as well as an error may keep its name, suppressed with what it is.
- **errchkjson:** check `json.Marshal`'s error. Suppress only where the value can't fail to
  marshal, and say what it is.
- **errorlint:** compare errors with `errors.Is` and `errors.As`. Choosing `%v` over `%w` is
  deliberate ([Errors](#errors)); suppress it with the reason.
- **gosec:** each rule is a security judgement. Suppress with the rule's ID and why it doesn't
  apply: `//nolint:gosec // G304: a code generator reads the file it's told to rewrite`.
- **revive:** a `time.Duration`'s name doesn't end in a unit; revive reads `RetryMin` as minutes,
  so `MinRetry`.
