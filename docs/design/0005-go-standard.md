# 0005 — Go as an org language

Status: proposed

Tracking issue: [#63](https://github.com/swimblocks/.github/issues/63).

## Context

Every SwimBlocks repo is Python today, and the standards — [0004](0004-uv-standard.md), the
ruff selection, the reusable CI — are written for Python alone. The first service that more
than one repo will call, `swimblocks/fetch-service` (signed, polite, cached HTTP fetches for
the crawlers), is a long-running backend rather than a CLI or a batch job.

Go suits that shape: one static binary, a small distroless image, fast cold starts when Cloud
Run scales to zero, and a standard library HTTP stack that needs little on top. It is also the
language the maintainer prefers to write. If Go is not admitted when the first service that
suits it arrives, the org will drift into being Python-only by default; this record makes it a
first-class option instead, with the same level of standardisation Python has.

Python is not being replaced.

## Design

### When to choose which

- **Go** for services and long-running backends, and wherever a single static binary is the
  natural deliverable.
- **Python** where its libraries are the reason: PDF and document parsing, data wrangling,
  Google Sheets glue, vision models.
- Neither is a rule; the repo's design says which it uses and why.

### Toolchain

- **Go version:** the current stable release. The standard names no version number, so it
  never needs updating; `CONTRIBUTING.md` and the create-repo script say "current stable
  release" too. In a repo, `go.mod`'s `go` directive is the single source of truth; CI reads
  it, and nobody repeats the version elsewhere. The
  [Go release policy](https://go.dev/doc/devel/release#policy) supports the two most recent
  releases, so a repo moves within six months of a new one; Dependabot's `gomod` updates
  prompt it.
- **Module path:** `github.com/swimblocks/<repo>`, the idiomatic path, which `go get` resolves
  without anything to host. It does tie the path to the git host, but only in name: our code
  lives under `internal/` and no other module imports it, so a move to another host is a
  one-commit find-and-replace per repo. A vanity path (a domain we serve `go-import` metadata
  from) would avoid even that, at the cost of hosting it; not worth it until a module is meant
  to be imported by others.
- **Commands**, identical locally and in CI:

  ```bash
  go build ./...
  go test ./...
  golangci-lint run
  ```

- **No vendoring.** `go.sum` is committed and is the lock, as `uv.lock` is for Python.

### Lint and format

[golangci-lint](https://golangci-lint.run/) v2, configured by a committed `.golangci.yml`:

```yaml
version: "2"
linters:
  default: standard        # errcheck, govet, ineffassign, staticcheck, unused
formatters:
  enable: [gofmt, goimports]
```

That is the Go counterpart of the ruff selection: defaults that catch real bugs, formatting
enforced by the formatter rather than reviewed. Additions go in the org standard
(`CONTRIBUTING.md`), not per repo.

### Layout

Standard Go project layout, kept small:

- `cmd/<command>/main.go` for each binary; the command directory is the binary's name and is
  `kebab-case` because it is the executable's name (`cmd/fetch-service/`).
- `internal/<package>/` for everything else. Packages are not importable from other repos
  unless there is a reason, which is then documented.
- Tests sit beside the code as `<file>_test.go`, the Go convention; fixtures go in the
  package's `testdata/` directory, which the Go tool ignores when building.

### Naming

The [naming guideline](../../CONTRIBUTING.md#naming-files-and-directories) applies, with one
place where Go's own rules win:

- **Source files** are `snake_case`: `web_bot_auth.go`, `web_bot_auth_test.go`.
- **Package directories** are a single lowercase word, because the package name must be a
  valid identifier and should match its directory. Choose a word that needs no compounding
  (`signing`, `politeness`, `cache`) rather than squashing words together (`webbotauth`) or
  abbreviating. When no single word fits, the package is probably doing two things.
- **Binaries and `cmd/` directories** are `kebab-case`, as executables are.

### Tests

`go test ./...`, with the standard `testing` package; table-driven tests are the norm. The
Faker rule for fixtures holds: Go repos use [gofakeit](https://github.com/brianvoe/gofakeit)
for synthetic people. Tests never touch live sites; HTTP is exercised against
`net/http/httptest` servers.

### Reusable CI

A new `reusable-go-ci.yml` beside the Python one. A repo's `ci.yml` is a thin caller:

```yaml
jobs:
  ci:
    uses: swimblocks/.github/.github/workflows/reusable-go-ci.yml@main
```

It runs `actions/setup-go` with `go-version-file: go.mod`, then `go mod tidy -diff` (fails when
`go.mod`/`go.sum` are out of date, the counterpart of `uv sync --locked`), `go build ./...`,
`go test -race ./...` and `golangci-lint` through `golangci/golangci-lint-action` at a pinned
linter version.

### Containers

Services build with a two-stage `Dockerfile`: `golang:<version>` to build with
`CGO_ENABLED=0`, then `gcr.io/distroless/static-debian12:nonroot`. The result is the binary,
CA certificates and nothing else — no shell, no package manager.

### Dependabot

Go repos use the `gomod` ecosystem alongside `github-actions`, and `docker` where there is a
`Dockerfile`.

### Devcontainers

The devcontainer for a Go repo uses the official Go feature and installs golangci-lint at the
CI's pinned version. The first Go repo lands the concrete snippet, which is then folded back
into [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Rollout

- `CONTRIBUTING.md` gains Go alongside Python under Quality gates, Dependencies and
  Environments; `docs/development.md` lists Go and golangci-lint as prerequisites for Go repos.
- `reusable-go-ci.yml` lands with this record.
- `scripts/create-repo.sh` prints the Go CI caller as well as the Python one in its next steps,
  and says to start on the current stable Go release.
- **`swimblocks/fetch-service` is the first Go repo**, and its CI is the first real exercise of
  the reusable workflow.

## Verification

- `actionlint` passes on `reusable-go-ci.yml`.
- **Not yet verified:** the workflow on a real runner. That happens with `fetch-service`'s first
  PR.

## Open items

- The devcontainer snippet, as above.
- Whether a shared Go library repo is ever wanted (for example, a client for `fetch-service`).
  Not until a second Go repo needs one.
