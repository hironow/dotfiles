# CLIs for review, search, data extraction, and process inspection

Install Hunk, ripgrep (`rg`), fd, sd, mq, witr, jq, Mike Farah's yq, and fq from the shared mise configuration.
[`config/mise/config.toml`](../config/mise/config.toml) is the source of truth for versions.
Normal setup installs them via `install.sh` on Mac, Linux, and WSL, and via `just deploy` called from `bootstrap.ps1` on Windows.
jq also uses a pinned version from `aqua:jqlang/jq`.
Exclude jq from the Mac Homebrew restore list and standardize on mise.
Before removing an existing Homebrew installation, verify that the mise version works from a normal shell.
Keep existing aliases and the Windows bootstrap jq used before mise is installed.

## Managing AWS CLI v2

Manage the AWS CLI from the official `http:aws` distribution using mise.
The pinned version is 2.39.6, verified against the official `v2/version.txt` and release artifacts as of 2026-11-07.
Do not fall back automatically to PyPI AWS CLI v1 or the Homebrew version.

```shell
env MISE_GLOBAL_CONFIG_FILE="$PWD/config/mise/config.toml" \
  mise -C / install http:aws@2.39.6
just aws-list
```

Select the same Universal package for Mac arm64 and x64, and the glibc ZIP for Linux/WSL x64 and arm64.
Windows is outside this backend's scope and keeps using the existing standalone version.
This configuration has not been tested on musl, other CPUs, or the Windows MSI.
On POSIX, `aws-list` explicitly uses this checkout's mise version so it does not run an older AWS binary on PATH.
Windows invocation remains unchanged.
Both only list local profiles and do not check remote permissions or log in.

mise verifies each artifact's SHA256 before extraction.
On Mac, it also verifies Apple trust and Developer ID Team `94KV3E626L`, then extracts the complete bundled runtime into mise's dedicated directory.
Do not trust the target path from environment variables alone; compare the physical path against the install destination authorized by the running mise instance.
Do not use the package installer or root privileges, and leave existing `/usr/local/aws-cli` and `~/.aws` untouched.
Use mise itself from a standard location (such as `~/.local/bin`), and do not run any program from the downloaded payload to inspect the install destination.

Update the version, all URLs and checksums, and the Mac hook's version and digest together.
Verify the Apple signature on Mac and the AWS CLI Team signature on Linux (fingerprint `FB5DB77FD5C118B80511ADA8A6310ACC4672475C`) before accepting any hash.
Before execution, compare every path, type, content, executable bit, and symlink target between the signed payload and the installed directory.
Also verify that checksum mismatches, swapped install destinations, and signature failures are rejected as incomplete installs and can be retried.
Because the 2.39.6 Mac payload contains no symlinks, the hook rejects any new links.
If the distribution layout changes, re-verify the layout rather than relaxing the checks.

On this Mac, all 8,706 entries matched and ARM64 startup succeeded.
For Linux, signatures and ELF CPU types were checked, which does not mean execution on Linux or Intel Mac was tested.
Processes started before activating mise do not get an updated PATH automatically.
Use a fresh mise environment or the explicit recipe, and do not delete the old root-owned AWS installation without separate permission.

References: [AWS installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), [official current version](https://awscli.amazonaws.com/v2/version.txt), [mise HTTP backend](https://mise.jdx.dev/dev-tools/backends/http.html).

## Google Colab CLI

`colab` is a CLI for using Google Colab CPU, GPU, and TPU runtimes from the terminal ([googlecolab/google-colab-cli](https://github.com/googlecolab/google-colab-cli)).
Install it via mise as `pypi:google-colab-cli` and pin it to 0.8.0. Read the changelog before bumping the version.
Because upstream supports only Linux and macOS, mise does not install it on Windows.
Authentication to the Colab API uses Application Default Credentials (`--auth adc`) by default. You can also use `--auth oauth2` with an OAuth client config file (default `~/.colab-cli-oauth-config.json`, per upstream README).

## Permanent CLIs and the 7-day cooldown

Cooldown exceptions apply only to permanent primary CLIs managed by dotfiles and dependencies inside each CLI's dedicated install environment.
[`ROOT_AGENTS_docs_agents_dependency-policy.md`](../ROOT_AGENTS_docs_agents_dependency-policy.md) is the source of truth for this policy.
Keep pinned versions, LTS, and beta selections as they are, and do not bulk-update existing CLIs with this change.

| Target | Current configuration and boundary |
| --- | --- |
| Host mise-managed CLIs, just, uv | `minimum_release_age = "0d"`. Do not add a 7-day check to mise's own bootstrap either |
| Permanent npm CLIs | `bun_args = "--minimum-release-age=0"` per declaration. Also covers dependencies in each CLI's dedicated environment |
| headroom | `--exclude-newer 0d` in its dedicated uv tool environment. Keep Python 3.13, extras, and pinned version |
| Podman 5+ | Required permanent CLI. Do not add a 7-day check to Homebrew, Linux OS packages, or Podman's dedicated winget path |
| podman-compose | Pinned to 1.6.0 on host and in images. Dedicated uv tool environment uses `--python 3.13 --exclude-newer 0d`, covering dependencies |
| Google Colab CLI | Pinned to 0.8.0 on host only. Dedicated uv tool environment uses `--python 3.13 --exclude-newer 0d`, covering dependencies. Linux and macOS only |
| devcontainer CLI | Keep existing pin at 0.90.0 on host and in images; CI uses the same source of truth. Dedicated npm environment dependencies also use 0 days |
| Homebrew, Scoop, verified bootstrap | No 7-day check in this repo. Separate from upstream catalog update timing or pinned versions |
| Machine-level npm and uv settings | Keep existing `min-release-age=7` and `exclude-newer = "7 days"` |
| Repo Python dependencies | Keep 7-day cooldown per project. Keep existing exceptions for ruff/ty |
| LSP/MCP, one-off uvx/bunx, CI-only tools, marketplace/plugin | No change. Evaluate new exceptions individually |
| devcontainer frozen generation | Keep existing versions and the single generator. Add only provider and devcontainer CLI declarations without bulk-updating |

Do not assume that having an npm config alone enables Bun's cooldown.
In an isolated global install test with Bun 1.4.4, a 7-day setting in npmrc alone did not reject newer dependencies.
Explicit 7-day Bun flags and 7-day uv settings rejected newer dependencies, while CLI-specific 0-day settings installed both the package and its dependencies.
Also test controls for package-only exceptions, removing the 0-day setting, and backdating only dependency publish timestamps.
Do not set global npm/uv settings to 0 days, and do not apply this CLI exception to repo dependencies.

## Installing from this checkout

The following recipe selectively installs the 9 tools from this checkout and checks each version.
It does not modify the machine's global mise configuration.

```shell
just cli-tools-install
```

Even if an older shell's PATH points to a different jq, you can verify the pinned version from the checkout root:

```shell
env MISE_GLOBAL_CONFIG_FILE="$PWD/config/mise/config.toml" \
  mise -C / exec aqua:jqlang/jq -- jq --version
```

| Tool | macOS | Linux / WSL | Windows native |
| --- | --- | --- | --- |
| Hunk | arm64, x64 | glibc, arm64, x64 | x64, mise 2026.8.6 or later |
| rg, fd | arm64, x64 | arm64, x64 | arm64, x64 |
| sd | arm64, x64 | arm64, x64 | x64 only |
| mq | arm64 only | GNU/glibc build, arm64, x64 | arm64, x64 |
| witr, fq | arm64, x64 | arm64, x64 | arm64, x64 |
| jq | arm64, x64 | arm64, x64 | x64 (uses x64 build on arm64) |
| mikefarah/yq | arm64, x64 | arm64, x64 | x64 only with this aqua backend |

The table shows upstream artifact availability and selected backends, not hardware testing on every platform.
All 9 tools install cleanly on Mac arm64, glibc Linux/WSL arm64 and x64, and Windows native x64.
On Intel Mac, both `mise install` with the shared config and this recipe skip mq and install the other 8 tools.
The recipe prints a message noting that mq is unavailable.
On Windows arm64, the Hunk, sd, and yq backends are outside this shared set; on musl Linux, Hunk and this mq configuration are unavailable.
Do not fall back automatically to building from source.

Except for mq, fetch upstream binaries via mise's aqua backend.
Specify `aqua:mikefarah/yq` for yq and `aqua:wader/fq` for fq to avoid confusion with Python yq or other tools of the same name.
For mq, use the GitHub backend to select only the main raw binary and install it as `mq` (`mq.exe` on Windows).
Do not select auxiliary CLIs or deb/rpm packages in the same release.
Do not add a Node or Rust build toolchain.

mq pins SHA256 checksums for each of the 5 supported targets, and mise verifies them before execution.
When updating, update the version and all target checksums together, and cross-check the release API digest, upstream `checksums.txt`, and the hash of the downloaded binary.
Checksums from the same host detect tampering but do not prove publisher provenance.
The other tools use aqua registry checksum verification.

Update mise-installed versions using mise.
In sd v1.1.0, `sd --version` prints `1.0.0` because upstream did not bump the version number ([tag manifest](https://github.com/chmln/sd/blob/v1.1.0/Cargo.toml)).

## Extracting only what agents need

Use `jq` for JSON, `yq` for YAML, `fq` for binary formats, `mq` for Markdown, and `witr` for process ancestry.
Extracting only the relevant slice before passing data to the model reduces the need to read entire files or full process lists.
Latency and token savings depend on the input and operation, so fixed gains are not guaranteed.

See [`ROOT_AGENTS_docs_agents_cli-tools.md`](../ROOT_AGENTS_docs_agents_cli-tools.md) for command examples, defaults, and `witr` exit codes.
The source of truth for agents is `ROOT_AGENTS.md` and this spoke; do not edit deployed copies directly.
Deploy per [`docs/agent-sync.md`](agent-sync.md), checking target home diffs with `just sync-agents-preview` first.
Do not alias over existing `grep`, `find`, or `sed`, and verify behavior per call site when migrating scripts.

References: [Hunk install requirements](https://github.com/modem-dev/hunk/tree/v0.25.0#install), [mise GitHub backend](https://mise.jdx.dev/dev-tools/backends/github.html), [mise registry](https://mise.jdx.dev/registry.html).
