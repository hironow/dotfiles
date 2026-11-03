# Go tooling

Read this when you write or change a **service**, a CLI, a tool, or any new Go
code. AGENTS.md sets the language choice: new code is Go, and Rust only when Go
does not fit (docs/agents/rust-tooling.md). Existing Python tooling and bun
frontends stay where they already are. A prototype is new code too: write it in
Go, not Python, so that it never has to be ported before it can be made fast.
The one exception is GPU work that targets CUDA, through PyTorch or another
CUDA library, which may be Python (AGENTS.md).

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
- **HTTP, crypto, sync, testing, log/slog**: standard library.

`golang.org/x/*` is the exception when a package lives there before it moves
into the standard library. Treat it as Class 1, not as a niche utility. Dependency
classes: docs/agents/dependency-policy.md.

## JSON: `github.com/goccy/go-json` (required)

JSON is the one exception to "standard library first". go-json is faster than
the standard library with the same API, and one JSON implementation in every
repository keeps the behavior the same everywhere. In Go code the repository
owns, never import `encoding/json`, `encoding/json/v2`, or
`encoding/json/jsontext`:

| Standard library | Use instead |
| --- | --- |
| `encoding/json/v2` | `github.com/goccy/go-json/v2` (new code) |
| `encoding/json/jsontext` | `github.com/goccy/go-json/jsontext` |
| `encoding/json` | `github.com/goccy/go-json` (code that keeps the v1 API) |

Replace existing uses actively, one module at a time:

- When you change a module that still imports a standard-library JSON package,
  swap the whole module first, in its own `refactor:` commit before the
  behavior change. A large module may get its own PR. Do not wait for a
  rewrite.
- Swap every JSON import of the module in that commit, and add go-json to
  `go.mod` and `go.sum`. go-json's types are its own, not aliases of the
  standard library's, so a half-swapped module breaks without an error:
    - `MarshalJSONTo` / `UnmarshalJSONFrom` methods take the `Encoder` /
      `Decoder` of `github.com/goccy/go-json/jsontext`. With
      `github.com/goccy/go-json/v2`, methods that take the standard library's
      are not called (the v1 package still calls them on Go 1.27). Swap them
      anyway, so the module does not depend on which package marshals it.
    - `errors.As` / `errors.Is` targets become go-json's error types
      (`SyntaxError`, `SemanticError`, ...). `RawMessage`, `Number`, `Token`,
      and `Delim` stay the standard library's.
- Before you swap, grep the module and its direct dependencies for
  `MarshalJSONTo` / `UnmarshalJSONFrom` that take `encoding/json/jsontext`. If
  the module holds code you must not swap (generated code, a third-party type
  or API bound to the standard library's JSON types), do not half-swap it: stop
  and report it.
- Prove the swap changed nothing: `go build ./...`, `go vet ./...`, and
  `go test ./...` pass with the tests and fixtures unchanged, and so does the
  repository's build for every OS and CPU it ships. If an option or function
  you use has no go-json counterpart, stop and report it; never fall back to
  the standard library in silence.
- Never swap code another project owns: git submodules, vendored copies you do
  not maintain, the module cache.
- Where a lint rule (golangci `depguard`) is set up, it blocks the
  standard-library imports. Elsewhere, find what is left with
  `grep -rn --include='*.go' '"encoding/json' <module>`.

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

## Measure before you optimise

- Find where the time goes before you change anything for speed. Use the
  standard tools: `go test -bench`, `-cpuprofile` and `-memprofile` with
  `go tool pprof`, and `runtime/trace`.
- If most of the time is the network, a disk, or another service, making this
  code faster changes little. Fix the slow dependency or the call pattern first.
- Keep hot state in plain in-memory data structures owned by one goroutine
  by default. If the state must survive a restart, stay consistent, or be
  recoverable, meet that requirement from the start (an embedded database is
  fine). Add complexity for speed (shared memory, lock-free queues, more
  goroutines, a database or cache for speed) only when a measurement shows the
  simple version is the bottleneck.
