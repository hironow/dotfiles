# 0050. Pin Go sources to LF via `.gitattributes` (go-lint on Windows)

**Date:** 2026-10-02
**Status:** Accepted

## Context

`just check` failed on the maintainer's Windows native host at the `go-lint`
leg:

```text
emulator\bigtable-cli\main.go:1:1: File is not properly formatted (gofumpt)
package main
^
1 issues:
* gofumpt: 1
```

This is ADR 0020's failure mode in a second toolchain, so the audit and the
shape of the fix are the same. `core.autocrlf=true` (the Windows default, also
true on this host) writes the working tree as CRLF while the index holds LF.
gofmt and gofumpt parse a CRLF file as "not properly formatted" and do not care
that the bytes match the blob.

`go-lint` runs both golangci-lint entry points in every module
(`git ls-files '*go.mod'`, 7 modules at landing time):

```bash
golangci-lint run --config .golangci.yaml ./...
golangci-lint fmt --config .golangci.yaml --diff ./...
```

`.golangci.yaml` enables gofumpt under `formatters`. Measured on a CRLF
`emulator/bigtable-cli/main.go`: `run` reports the message above, and
`fmt --diff` prints the whole file as changed (370 of 370 lines). Either one
fails the recipe through `set -euo pipefail`.

A `git ls-files --eol '*.go'` audit at landing time:

- 8 tracked `.go` files, every one `i/lf w/crlf attr/` — the **index** is
  already LF; only the Windows working tree differs.
- Zero `i/crlf`. No blob content changes; only the operator's checkout.
- `git show HEAD:emulator/bigtable-cli/main.go | gofmt -d` prints nothing, so
  the committed source is formatted and the CR is the whole problem.
- The Linux CI runner has no autocrlf, so CI is green and only local Windows
  fails — the asymmetry ADR 0020 documented for shellcheck.

## Decision

Add to `.gitattributes`:

```gitattributes
*.go   text eol=lf
```

Scope stays deliberately narrow, following ADR 0020: no repo-wide
`* text=auto`, and the existing `*.sh` / `*.bash` / `dump/scoop.json` rules
stay as they are. ADR 0020 covered shell scripts; this record covers Go
sources, and the `.ps1` case that record deferred is still not covered (the
repo has none).

### Existing Windows checkouts need a forced re-checkout

The pin only takes effect when git writes the file. For a path git considers
stat-clean, both `git checkout -- '*.go'` and `git checkout-index -f -- '*.go'`
are no-ops — measured here: after each, the file was still CRLF. Remove the
files first. That discards uncommitted Go edits, so check first:

```bash
git status --short -- '*.go'   # must be empty — the next line discards edits
git ls-files -z '*.go' | xargs -0 rm --
git checkout -- '*.go'
```

A fresh clone needs nothing. `git add --renormalize .` is index-side only and
staged zero content changes at landing time, as the audit predicts.

## Enforcement inventory

- **`.gitattributes`**: one rule plus a comment block citing this ADR.
- **`tests/unit/test_gitattributes_eol.py`**: the file already asserted
  `git check-attr eol` for the generated artifacts; a second case now asserts
  it for **every** tracked `*.go`, not a sample, so a new Go file is covered on
  arrival. ADR 0020 declined to add a test because shellcheck already failed
  loudly on Windows and `.gitattributes` was "the single source of truth". That
  reasoning does not carry over: the `git check-attr` precedent arrived after
  that record (13e1aa7, PR #215, 2026-07-05), and `go-lint` is green on CI, so
  a dropped `*.go` rule would break Windows alone, silently for everyone else.
- **No Go source change**: all 8 blobs are LF already.
- **Measured end state**: `just go-lint` prints `0 issues.` for all 7 modules
  with the working tree pinned to LF, and reproduces the gofumpt failure the
  moment one `.go` file is CRLF again.

## Consequences

**Positive**

- Windows native operators can run `just check`, `just lint` and the pre-push
  `just-check` hook without `--no-verify` and without skipping `go-lint`.
- Behaviour no longer depends on the operator's `core.autocrlf` setting.
- The `just check` failure that could not be fixed from a Windows host is
  closed, and the regression is caught by a test rather than by a host.

**Negative**

- An operator who edits a `.go` file in a CRLF-only editor (notepad.exe) gets
  LF back on save / commit. Modern editors honour `.gitattributes`, and gofmt
  rewrites the CR away on the next format anyway.
- The one-time re-checkout above is manual and git gives no hint it is
  outstanding: the working tree looks clean either way.

**Neutral**

- gofmt rejecting CRLF is upstream behaviour, not a bug; pinning the checkout
  is the supported fix.
- The `*.go` rule also covers `tools/simple-server/main_test.go`, so Go test
  files go through the same formatter leg as production code.
