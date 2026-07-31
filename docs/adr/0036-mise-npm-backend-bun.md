# 0036. Install mise `npm:` tools with bun, not the embedded aube

**Date:** 2026-07-31
**Status:** Accepted

## Context

`just clean-all && just deploy` left `claude` broken. The failure is not in
either recipe — it is in how mise installs the package.

mise's `npm.package_manager` defaults to `auto`, which uses its **embedded
`aube`** package manager (virtual-store layout, pnpm-style). claude-code ships
a **263 MB native binary** that its `postinstall` (`install.cjs`) puts in
place; `config/mise/config.toml` already passed `npm_args =
"--ignore-scripts=false"` precisely so that script would run. Under aube it
runs and still produces nothing usable:

```
$ ls -la .../npm-anthropic-ai-claude-code/2.1.215/node_modules/@anthropic-ai/claude-code/bin/
-rwxr-xr-x  500 claude.exe          # a stub, not the binary

$ .../2.1.215/node_modules/.bin/claude --version
TypeError [ERR_UNKNOWN_FILE_EXTENSION]: Unknown file extension ".exe"
  for ...\aube\virtual-store\@anthropic-ai+claude-code@2.1.215\...\claude.exe
```

The `.bin` shim execs `node claude.exe` — it treats the native binary as a
JS entrypoint, because the binary was never unpacked into the real path.

**Nothing reports this.** The install succeeds, `mise ls` looks healthy, and
the box keeps working — but only because a stray npm-global copy under
`installs/node/<ver>/` shadows the mise one on PATH. `just doctor` correctly
flags that copy as rogue and recommends `just prune-rogue-npm-globals`; on this
host that prune was **the thing that would break `claude`**, since it removes
the only working copy and leaves the 500-byte stub behind. The advertised
repair was the destructive operation.

Measured both ways on the same version:

| backend | `bin/claude.exe` | invocation                  |
| ------- | ---------------- | --------------------------- |
| aube    | 500 B            | `ERR_UNKNOWN_FILE_EXTENSION` |
| bun     | 263,931,552 B    | `2.1.218 (Claude Code)`      |

The other `npm:` tools were unaffected — `codex` 0.144.6, `copilot` 1.0.71 and
`pi` 0.80.10 all run fine under aube. They are plain JS packages; claude-code
is the only one shipping a native binary through a postinstall, so it is the
only one aube's layout defeats.

## Decision

Set `[settings.npm] package_manager = "bun"` in `config/mise/config.toml`.

`npm.package_manager` accepts `auto` / `npm` / `aube` / `aube_cli` / `bun` /
`pnpm`. **bun** is the only choice that both fixes the unpacking and stays
inside this repo's rules: `npm`, `pnpm` and `yarn` are barred outright
(ADR 0027), so picking bun costs no new exception — it is already the
sanctioned Node package manager here.

`npm_args = "--ignore-scripts=false"` stays. bun accepts it, and it remains
correct intent: the postinstall is what puts the binary in place.

## Consequences

- `claude` now works from mise's own install, so pruning the rogue npm-global
  copy is safe. Before this, `just prune-rogue-npm-globals` broke it.
- **Existing installs are not migrated.** A tool already unpacked by aube stays
  broken until it is reinstalled — changing the setting alone does nothing.
  Repair one with:

  ```sh
  mise uninstall "npm:<pkg>@<ver>" && mise install "npm:<pkg>@<ver>"
  ```

  Done here for claude-code 2.1.215 (500 B → 256,247,968 B, and its shim now
  answers `2.1.215 (Claude Code)`).
- The other three CLIs keep their aube-installed copies until their next
  version bump, at which point they come in via bun. They work today; verify
  with `codex --version` / `copilot --version` / `pi --version` after an
  upgrade, since bun is a different unpacker.
- This does not address **why** the rogue npm-globals exist (three remain:
  codex and claude-code under node 24.15.0, claude-code under 24.18.0). It only
  removes the reason they were load-bearing.
