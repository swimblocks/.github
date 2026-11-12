# 0006 — APIs follow the AEPs

Status: proposed

Tracking issue: [#64](https://github.com/swimblocks/.github/issues/64).

## Context

Until now SwimBlocks repos have been CLIs, batch jobs and scripts; none exposed an API for
another program to call. `swimblocks/fetch-service` will be the first: the crawlers in
`swim-meet-almanac` and `swim-club-tech-survey` will call it, and so will a club-discovery crawl
after it. Once two repos depend on an API, its shape is expensive to change, so the rules for
designing one should be settled before the first is written, not inferred from it afterwards.

[API Enhancement Proposals](https://aep.dev) (AEPs) are a community-maintained set of API design
guidelines grown out of Google's AIPs, with contributors from Google, Microsoft, Roblox and IBM.
They cover the decisions every API has to make — resource names, standard methods, pagination,
errors, field names, long-running operations — and they come with linters for both protocol
buffers and OpenAPI. They are naming and design guidance, independent of the language or
framework that serves the API.

## Design

### Scope

The rule applies to **APIs**: an HTTP or gRPC interface one program calls, whether the caller
is another SwimBlocks repo or something outside the org. It does not apply to CLIs, to
libraries' in-process interfaces, or to files a job writes for another to read (those are data
formats, covered by each repo's design).

### The standard

- **APIs follow the AEPs, keeping up with current editions within reason.** AEP editions are
  stable once published (`aep-2026` is current; `aep-2028` is in preview). A brand-new API
  follows the latest stable edition. An existing API is not redesigned because a newer
  edition exists; when it changes, whether to adopt newer guidance for the change is a
  judgement call made in that change's design.
- **Where an AEP says *should*, we do it** unless the design says why not. Deviations are
  listed in the design, each with its reason, so a reviewer can see them in one place.
- **Resource-oriented first** ([AEP-121](https://aep.dev/121)). An API is designed as
  resources with paths ([AEP-122](https://aep.dev/122)) and standard methods
  ([AEP-131](https://aep.dev/131)–[135](https://aep.dev/135)); a custom method
  ([AEP-136](https://aep.dev/136)) is used only when no standard method fits, and the design
  record says why.

### Definition and linting

Every API has a committed, machine-readable definition, and CI lints it.

- **Protocol buffers or OpenAPI 3.1 is the source of truth, and protobuf-first is
  preferred.** `.proto` definitions are what the reviewer prefers to read; OpenAPI-first is
  allowed where protobuf would be awkward, with the reason given in the design.
  - **Protobuf-first:** `.proto` files with
    `google.api.http` annotations ([AEP-127](https://aep.dev/127)) so the API is also served as
    HTTP/JSON. CI runs [aep-dev/api-linter](https://github.com/aep-dev/api-linter).
  - **OpenAPI-first** (natural for, say, a FastAPI service): the OpenAPI document is generated
    from the code and committed, so a change to the API shows up in the diff. CI runs the
    [aep-openapi-linter](https://github.com/aep-dev/aep-openapi-linter) Spectral ruleset.
- **Every HTTP API publishes an OpenAPI 3.1 document** ([AEP-101](https://aep.dev/101)), generated
  from the `.proto` files for protobuf-first repos. It is what callers read, and the OpenAPI
  linter runs on it in either case.
- **Linter versions are pinned.** The protobuf linter does not follow semantic versioning, so a
  floating version could turn a green `main` red on untouched code; Dependabot moves the pins.
- **Suppressing a lint rule** is done inline with the rule's name and a comment giving the
  reason, and the deviation goes in the design as above.

### Conventions the AEPs leave to us

- **Versioning:** the major version is the first path segment (`/v1/...`) and the protobuf
  package suffix (`swimblocks.fetch.v1`). Within a major version, changes are backwards
  compatible ([AEP-180](https://aep.dev/180) for protobuf; the same rules for OpenAPI). A
  breaking change is a new major version, served alongside the old one until its callers move.
- **Service names:** an API is identified by the repo that serves it
  (`fetch-service`), and its protobuf package is `swimblocks.<api>.v<N>`.
- **Errors** follow [AEP-193](https://aep.dev/193): RFC 9457 problem details
  (`application/problem+json`) over HTTP, and `google.rpc.Status` with canonical codes over gRPC.
- **Authentication** is not part of the AEPs. Service-to-service calls inside our Google Cloud
  use Cloud Run IAM: the caller's service account presents a Google ID token and the service
  grants `roles/run.invoker` per caller. An API that needs anything else says so in its design.

### Review

The API definition is the part of a change that is hardest to undo, so:

- A new API, or a new method or resource on one, is designed in the design record for the
  feature or change that needs it, not in a separate API document. That record shows the
  resource model, every method's request and response, and any deviations.
- PRs that change an API definition need the author's explicit review of the definition
  itself, not just a green linter.

## Rollout

- `CONTRIBUTING.md` gains a short "APIs" section stating the standard and linking here.
- **`swimblocks/fetch-service` is the first API.** It lands the lint configuration for its
  definition format; once a second API exists, the shared parts move into a reusable workflow
  here, as Python CI did.

## Verification

- The fetch-service design record is reviewed against this standard before its API is
  written, and its CI runs the linters above.

## Open items

- Whether to publish client libraries or let callers use the OpenAPI document directly. Not
  until a caller finds plain HTTP/JSON awkward.
- A reusable API-lint workflow, once there is a second API.
