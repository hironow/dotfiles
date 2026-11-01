# mise-versions

The only writer of the image's frozen tool versions.

`config/mise/image-tools.toml` is the source. It holds the versions the
devcontainer bakes into `/etc/mise/config.toml` or fetches as verified
tarballs, and the versions `install.sh` uses on a bare Linux host before mise
exists. This command writes those versions into the two scripts that carry
them, and reports drift between the source and the committed files.

## Usage

```bash
just mise-versions-check   # report drift; `just lint` and `just check` run it
just mise-versions-sync    # rewrite the generated regions after editing the source

# another checkout
mise exec -- go run tools/mise-versions/main.go check --root /path/to/dotfiles
```

Without `--root`, the checkout is found from the location of `main.go`, so the
working directory does not matter.

## What it writes

- `.devcontainer/features/dotfiles-tools/install.sh`: the body of the
  `/etc/mise/config.toml` heredoc, plus `UV_VERSION`, `JUST_VERSION`, and
  `SHELDON_VERSION`.
- `install.sh`: `_mise_ver` and `_just_ver`.

Everything else in both files is hand-written.

## What it rejects

A version that can move is a bug in a frozen image, so it rejects `latest`,
`lts`, partial versions (`24`), prefixes (`prefix:24`), and the empty string.
Every `[tools]` and `[fetch]` tool must also be in `config/mise/config.toml`.
Where the host pins an exact version, the two must match. Each version lives in
exactly one of `[tools]`, `[fetch]`, and `[bootstrap]`.

A validation or render error writes nothing. A disk error during `sync` can
leave one file written and the other not.

## Design

It is Go and runs with `go run`, not as a distributed binary
([ADR 0060](../../docs/adr/0060-frozen-image-generation-has-one-source.md),
[ADR 0061](../../docs/adr/0061-version-generator-in-go.md)). Go's standard
library has no TOML reader, so `main.go` parses only the subset these files
use and fails on anything else. It reads only the `[tools]` section of the
host config.

Two test suites check it: `main_test.go`, and
`tests/unit/test_mise_versions.py`, which runs the CLI and reads the output
back with Python's `tomllib`.
