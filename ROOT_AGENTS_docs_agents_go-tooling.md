# Go tooling

Read this when you write or change a **service**, a CLI, a tool, or any new Go
code. AGENTS.md sets the language choice: new code is Go, and Rust only when Go
does not fit (docs/agents/rust-tooling.md). Existing Python tooling and bun
frontends stay where they already are.

## Minimum version

- **Go 1.27 is the minimum.** Use the newest stable Go that the module
  compiles with (`go` directive ≥ 1.27). The repo's `go.mod` / `go.work` is the
  source of truth; an older Go in the environment makes CodeQL extraction fail.
- Use one module path per Go tree. `toolchain` follows the minimum version
  unless you need a newer patch.

## Standard library first

A third-party module needs a platform reason (a Cloud client, a protocol SDK).
Otherwise use the standard library, including packages new in this minimum
version:

- **UUID**: `uuid` (`uuid.New`, `uuid.NewV7`, `uuid.Parse`). Not
  `github.com/google/uuid`.
- **JSON**: `encoding/json/v2`. Go 1.27 provides it without an experiment
  flag. New marshal/unmarshal code uses v2; existing `encoding/json` code stays
  until that code is migrated.
- **HTTP, crypto, sync, testing, log/slog**: standard library.

`golang.org/x/*` is the exception when a package lives there before it moves
into the standard library. Treat it as Class 1, not as a niche utility. Dependency
classes: docs/agents/dependency-policy.md.

## Quality gate

Lint and format with **golangci-lint v2**: one tool, one config.

- `golangci-lint run` lints (includes `go vet`, staticcheck, errcheck, ...).
- `golangci-lint fmt` formats, with **gofumpt only**. If you also enable
  goimports, `fmt` and `run` disagree on import groups.
- Copy the dotfiles `.golangci.yaml` to the module root and change only build
  tags, `gofumpt.module-path`, and per-path exclusions. Change the linter set in
  one place, not in each repo.
- Wire it into the root `justfile`: `go-lint` (`golangci-lint run ./...` and
  `golangci-lint fmt --diff ./...`, called from `just check`) and `go-fmt`
  (`golangci-lint fmt ./...`).
- Run tests with `go test ./...`. Use deterministic clocks instead of wall-clock
  sleeps. HTTP tests use `httptest` or bind `:0`. CI pins golangci-lint and
  installs the Go version that the module's `go` / `toolchain` directive requires.

## Ship binaries for every device

Build one static binary per target, with no C toolchain, for example
`CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -o
dist/<name>-linux-arm64 ./cmd/<name>`. Cover linux/amd64, linux/arm64, darwin/arm64, and windows/amd64. Name each
output `dist/<name>-<os>-<arch>`, with `.exe` added for Windows.

Put the target list in one `just` recipe. Keep `CGO_ENABLED=0`; a dependency
that needs cgo breaks cross-compiling, so it needs an explicit reason.
