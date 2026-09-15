# Go Tooling

Read this when writing or changing a **service**, or any new Go.
Language choice is in AGENTS.md: services are Go; Python tooling and bun
frontends stay where they already live.

## Floor

- **Go 1.27 is the floor.** Take the newest stable Go the module compiles
  (`go` directive ≥ 1.27). The repo's `go.mod` / `go.work` is the source of
  truth — a trailing environment Go fails CodeQL extraction.
- One module path per Go tree. `toolchain` follows the floor unless a newer
  patch is required.

## Stdlib first

A third-party module needs a platform reason (Cloud client, protocol SDK).
Prefer the standard library, including packages that arrived with this floor:

- **UUID**: `uuid` (`uuid.New`, `uuid.NewV7`, `uuid.Parse`). Not
  `github.com/google/uuid`.
- **JSON**: `encoding/json/v2` under `GOEXPERIMENT=jsonv2` (the v2 import is
  experiment-gated in 1.27). New marshal/unmarshal paths use v2; existing
  `encoding/json` stays until that path is migrated.
- **HTTP, crypto, sync, testing, log/slog**: stdlib.

`golang.org/x/*` is the exception when the stdlib package is still evolving
there; treat it as Class 1, not as a niche utility. Dependency classes:
docs/agents/dependency-policy.md.

## Quality gate

Lint and format through **golangci-lint v2** — one tool, one config:

- `golangci-lint run` = lint (subsumes `go vet`, staticcheck, errcheck, ...).
- `golangci-lint fmt` = format, **gofumpt only**. Enabling goimports alongside
  it makes `fmt` and `run` disagree on import groups.

Keep one golangci-lint v2 config shape (gofumpt-only formatters, standard
linters plus the usual extras). Copy it to the module root; change only
build-tags, `gofumpt.module-path`, and per-path exclusions. Evolve the
linter set in one place, not per-repo.

Wire into the root `justfile` and `just check`:

```just
go-lint:
    golangci-lint run ./...
    golangci-lint fmt --diff ./...

go-fmt:
    golangci-lint fmt ./...
```

The Claude `format-after-edit` hook still runs `gofmt -w` per file — that is
a convenience, not the gate. Tests: `go test ./...`. Deterministic clocks
over wall-clock sleeps; HTTP tests use `httptest` or bind `:0`.
CI pins golangci-lint and provisions the Go the module's `go` / `toolchain`
directive demands.
