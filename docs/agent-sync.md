# Distributing agent instructions (sync-agents)

This repository holds the source of truth for global instructions shared by all agents, and `just sync-agents` (`scripts/sync_agents.py`) distributes them to each agent's config directory.
Read this before changing `scripts/sync_agents.py`, `ROOT_*` files, or `.claude/settings.*.json`.

## Source files

Place source files in the repository root with a `ROOT_*` marker name so agents do not read them directly.

- **base**: `ROOT_AGENTS.md`. Short instructions always read by every agent
- **overlay**: `ROOT_CLAUDE.md`. Claude-only; loads base via `@AGENTS.md` at the top
- **spoke**: `ROOT_AGENTS_docs_agents_*.md`. Details read only when needed (TDD, commit, Python, etc.)
- **hooks**: `ROOT_AGENTS_hooks_*` and `.claude/settings.hooks.json`, which registers them. Mechanical enforcement via hooks. This is the single source for hooks; sync generates Codex registrations from it
- **settings fragments**: `.claude/settings.shared.json`, `.claude/settings.shared.{macos,linux,windows}.json`, and `.claude/settings.profiles/<key>.json` (ADR 0037)

Files or directories named `ROOT_AGENTS_<x>_<y>` are distributed to `<agent>/<x>/<y>` (converting `_` to `/`).

## Targets

| Source | Target |
| --- | --- |
| base | `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.claude*/AGENTS.md` |
| overlay | `~/.claude*/CLAUDE.md` |
| spoke | `<agent>/docs/agents/*` |
| hooks | Claude homes (`~/.claude*`) and Codex (`~/.codex`) |
| settings | Claude homes only |

`~/.gemini/GEMINI.md` is the global instruction file shared by Gemini CLI and Antigravity CLI (mise names the executable `antigravity`; its old name was `agy`) (google-gemini/gemini-cli#16058).
Existing distribution to gemini also covers Antigravity.

During distribution, references to `docs/agents/` in base are rewritten to absolute paths under that home.
Relative paths would resolve inside the active project and miss.

Direct edits to distributed files are overwritten on the next sync.
To change global rules, edit the source files and run `just sync-agents`.

## Merging hooks and settings.json

settings.json is merged in place so user keys are not broken (not tracked in the distribution manifest).

Hook blocks owned by sync are only those whose every command points to `<agent>/hooks/` or runs the agent-hook executable (`docs/plan/agent-hooks-go.md`).
The executable is the per-home stable path `.../dotfiles/agent-hooks/current/<home>/agent-hook` (a symlink to a release).
In both Claude and Codex, if a handler points directly to a release, keep it as user-owned (sync writes only the stable path).
The paths accepted by render are the same, determined by each harness's `registration.layouts` (both allow `stable` only).
On Windows, the name ends with `.exe`; on POSIX, it does not.
Only handlers that execute that absolute-path executable as the program in the shape render writes for that harness are counted (`_runs_agent_hook_release`).
In Claude, the only accepted shape is exec form (with `args`, and `command` is the path itself).
In Codex, the only three accepted shapes are sh `'...'` (`'` as `'\''`), PowerShell `& '...'` (`'` as `''`), and cmd `"..."`.
The program starts at the beginning of command, followed by one ASCII space or the end of command (matching what render writes; sh splits words only on space, tab, and newline, so NBSP and similar become part of the program name).
Nothing after the program is compared (even if the template changes, handlers written by an older template stay owned and are not duplicated on revert).
Handlers with members that render does not write are not counted even if command points to `<agent>/hooks/` (Claude writes only `type`, `command`, `args`, `timeout`, and `onFailure`; Codex writes only `type`, `command`, and `timeout`, while Codex's `commandWindows` changes what runs on Windows).
Paths containing characters that the harness interprets as non-path syntax are not counted.

- `%` and `!` in cmd.
- `${` in Claude exec form.
- `‘` `’` `‚` `‛` (read as single quotes) and `*` `?` `[` `]` (search for another executable if the path does not exist) in PowerShell.
- Control characters.

Windows paths compare `\` and `/` as the same separator, while POSIX paths compare verbatim (on POSIX, `\` is a filename character).
Commands that only mention that path in arguments, assignments, or redirects are kept as user-owned.
Owned blocks are replaced with the latest fragment on every run (changing a hook command does not leave duplicate old blocks behind).
User-created blocks are kept.
Files in `<agent>/hooks/` starting with a third-party installer header (`# installed by herdr`, etc., in `THIRD_PARTY_HOOK_HEADERS`) are treated as owned by that installer.
Those files are not deleted, and blocks calling them are not replaced.

Immediately after merging hooks, settings fragments are composed from four layers into one state and merged into settings.json.
Later layers win.

1. `settings.shared.json`: all OSes and profiles
2. `settings.shared.<os>.json`: current OS (empty if the file does not exist)
3. `settings.profiles/<AgentTarget.key>.json`: per profile
4. `<agent home>/settings.sync-local.json`: final machine-specific override (not tracked in git)

- `env` is replaced in full with the composed content (keys removed from fragments are also removed from settings.json). Put machine-specific `env` in layer 4. `settings.local.json` is only read at project scope, so it cannot hold user-scope overrides.
- Inside `settings`, later layers win per key. Only when both values are dicts is there a one-level deep merge (a profile can add other `permissions` keys while keeping shared `permissions.deny`).
- Top-level keys in settings.json are only added or updated (keys absent from fragments, such as `enabledPlugins`, are kept).
- List top-level keys removed from a fragment in its `retired` map (for example, `.claude/settings.profiles/work-c.json`) with each migration ID's key and every value the fragment ever wrote. sync evaluates each migration once per home, records evaluated IDs in `settings.sync-state.json` (sync-owned) before writing `settings.json`, and deletes the key if it still holds one of those values. Later re-sets survive, while pre-existing identical values cannot be distinguished, so put values to keep in layer 4.
- `skillOverrides` is `{}` in shared, leaving every skill at Claude Code's default `"on"` (show name and description in the list). Putting `{}` instead of deleting the key prevents stale values from remaining in each home. To hide a skill on a single machine, write it under `settings.skillOverrides` in that home's `settings.sync-local.json`.
- The fragments are the source of truth for `env`. The repo's `.claude/settings.json` has no `env` and inherits it from global.

## Changing hooks

The sources of truth for hooks are `ROOT_AGENTS_hooks_*.sh` and `ROOT_AGENTS_hooks_block-prohibited-commands.py` for the command guard.
Unit tests are in `tests/unit/test_agent_hooks.py`.
Direct edits to distributed `~/.claude/hooks/*` files are overwritten on the next sync.
Fix the source, add tests, then run `just sync-agents`.

There is a Go port of command guard, files guard, and secrets guard (`tools/agent-hooks`; plan in `docs/plan/agent-hooks-go.md`).
The binary `agent-hook <harness> pre --hook <id>` (guards and rtk) and `agent-hook <harness> post --hook formatter` read Claude, Codex, and agy payloads and respond in each harness's expected format (agy supports guards and formatter only).
For Pi, an extension running inside Pi (the shim; dotfiles does not distribute it yet) sends requests using the shim protocol (`tools/agent-hooks/shim/`), and the binary replies in the same protocol (guard, formatter, and rtk; rtk matches the behavior of vendored `config/pi/extensions/rtk.ts`, captured as a corpus by `just pi-rtk-corpus`).
Because Pi resolves tool paths before writing, the binary checks the same resolved paths (`tools/agent-hooks/internal/pipath`; Pi 1.4.0's own answers are captured as a corpus by `just pi-paths-corpus`).
Parity with the original guards is verified against the corpus in `tools/agent-hooks/internal/guardcorpus/`.
Per-harness definitions (payload schemas, responses, and per-hook support) live in `tools/agent-hooks/harnesses/` (`README.md` explains how to write them).
A conformance suite (`tools/agent-hooks/internal/conformance/`) runs the same scenario across all harnesses to flag definition errors.
On each run, the binary appends one line with fixed fields only to `$XDG_STATE_HOME/dotfiles/agent-hooks/logs/<UTC date>.jsonl` (default `~/.local/state/...`; paths, commands, and contents are omitted; not yet written on Windows). `just agent-hooks-log` displays recent rows as a table.
`just agent-hooks-build` builds a reproducible release binary for this machine at `~/.local/share/dotfiles/agent-hooks/releases/<release ID>/agent-hook` (only if `agent-hook selftest` passes; builds to the same path run one at a time; not yet built on Windows). `just agent-hooks-build check PATH` rebuilds and compares bytes. See "Wiring agent-hook (Claude)" below for wiring Claude homes to a release, and "Wiring agent-hook (Codex)" for Codex.
Whenever you change a guard, the rtk hook, the formatter, their tests, or `guard-codex.sh`, regenerate the corpus and update the Go side to match.
Regenerate command guard with `just command-guard-corpus`, files guard and secrets guard with `just file-guards-corpus`, binary payloads with `just hook-payload-corpus`, and rtk hook and formatter with `just tool-hooks-corpus`.
`tests/unit/test_command_guard_corpus.py`, `tests/unit/test_file_guards_corpus.py`, `tests/unit/test_hook_payload_corpus.py`, `tests/unit/test_tool_hooks_corpus.py`, and Go tests flag any drift.
Bugs in old scripts are fixed in the binary (owner's decision, 2026-11-04).
Fixes live as named patches on the old scripts in `scripts/old_script_fixes.py`, and regenerating a corpus runs both the old script and the fixed version.
Where answers differ, they get diff ID `fixed-<name>`, and the binary returns the fixed version's answer.
`tests/unit/test_corpus_differences.py` checks that every diff ID has a kind and reason, and Go corpus tests split subtests by `parity/` and the diff ID name (run `go test -run '/fixed-'` to inspect only the fixed cases).
Fixes that old scripts cannot reproduce (such as a guard blocking on hook panic) are registered in the same test as binary-only fixes, naming the Go test that verifies them.

To test a single hook, pass JSON on stdin.
`exit=2` means block, and `exit=0` means allow.

```sh
echo '{"tool_input":{"command":"npm install"}}' | bash ~/.claude/hooks/block-prohibited-commands.sh; echo "exit=$?"
echo '{"tool_input":{"file_path":"config.yml"}}' | bash ~/.claude/hooks/block-prohibited-files.sh; echo "exit=$?"
```

## Wiring agent-hook (Claude)

On macOS, Linux, and WSL, `just sync-agents` wires Claude homes (`claude`, `work-a` through `work-d`) to the agent-hook binary.
Registrations point in exec form to the per-home stable path `~/.local/share/dotfiles/agent-hooks/current/<home>/agent-hook` (a symlink to the release).
Native Windows is not wired yet; it leaves the current scripts registered and prints one line stating so.
Codex (`hooks.json`) wiring is covered in the next section.

Each sync run proceeds in this order (`scripts/agent_hook_sync.py`):

1. Acquire `~/.local/state/dotfiles/agent-hooks/switch.lock` (waits up to 30 seconds, then names the holder and stops). `hookrelease switch`, install, uninstall, and gc take the same lock.
2. Clean up all change records (`switch-<home>.json`) left by prior runs and print one line per record showing what was done (verify and delete if finished, roll back if in progress). If any record cannot be cleaned up, the entire run stops there.
3. If any settings fragment (`settings.shared.json`, OS variant, profile, or any home's `settings.sync-local.json`) contains `hooks`, stop without writing anything.
4. Build and verify the release (`hookrelease build` and `check`). If Go is missing or fails, continue without a release.
5. For each home, build a plan from a re-read state and re-read once more right before writing. If a home's state cannot be read (corrupt `settings.json`, malformed `hooks` such as a non-array, or a regular file at the link path), only that home stops.

The plan is one of the following, printing one line per home (`scripts/agent_hook_plan.py`):

- `register`: Rewrite the registration to match the release shape (initial wiring, template change, or when rtk's own hook `rtk hook claude` returns to an already-wired home; merge removes it).
- `link`: Keep the registration as is and move only the link to the new release.
- `nothing`: Nothing to change.
- `keep`: No release, but keep existing wiring (do not touch `hooks`, including positions and rtk's own hook).
- `scripts`: No release and home is not wired yet; keep current scripts.
- `uninstalled`: Home has the uninstall marker; keep current scripts.
- `stop`: State requiring human decision, such as being wired while the marker exists. Do not change that home's hook registrations (still deploy files and merge shared settings). Other homes proceed, and the run exits 1.

Changes that rewrite registrations (register, install, unregister) record the link, `settings.json`, and the uninstall marker as one transaction (`scripts/agent_hook_wiring.py`). Even changes that leave the marker unchanged (register) record it and verify it at every step (stopping if the marker is created mid-run).
If interrupted mid-way, the next run reconciles to either the old or new state.
When rolling back, only the `hooks` value in `settings.json` is restored, leaving other keys (shared settings from sync and values written by other programs) intact. Even if `settings.json` did not exist before the change, the file is not deleted and stays without `hooks`.
The link is not deleted, so Claude sessions that missed a settings reload can still follow it.
If another program modifies `hooks` mid-change, stop while keeping the record.
`settings.json` is written only once (combining hooks and merged shared settings; `settings.sync-state.json` is written first).
In a home where registration changes did not finish (rolled back, discarded, or stopped), nothing is deleted afterward so the reverted registration's target scripts are not removed.
On macOS, writes are flushed to disk with `F_FULLFSYNC` (`fsync` stops at the drive cache).

- `just agent-hooks-uninstall <home>...`: Restore current script registrations and mark the home. Marked homes keep using scripts across syncs. Links and releases are kept. Works even without a release.
- `just agent-hooks-install <home>...`: Remove the marker and re-wire. Requires a release.
- `just agent-hooks-gc [--delete]`: List unreferenced releases. A release is considered referenced if a home link points to it, or its ID appears literally anywhere in a Claude or Codex registration file or change record (scans both raw bytes and strings parsed from JSON the same way the harness does, including `$HOME`, `~`, relative paths after `cd`, and IDs in variables; keeps on doubt). Names assembled by a shell at runtime from fragments cannot be tracked. If the layout is not what hookrelease creates (for example, `releases` is a symlink), stop without deleting anything. Deletions happen only with `--delete`, and re-verify right before deleting. Safe to run even while Codex is running (sync does not delete groups naming a release, and gc keeps releases they name).
- `just agent-hooks-test-installed [home]`: Verify the release pointed to by that home's link with `hookrelease check`, then run agent-hook process tests against it.
- `just sync-agents-preview`: Neither locks, writes, nor builds a release. Plans against any existing release and prints unknown where a build would be needed.
- doctor reports marked homes as INFO and leftover records as WARN.

In Claude homes, sync owns only stable-path registrations. Blocks pointing directly to a release stay user-owned.
`scripts/sync_agents.py` runs in the uv project environment (not as a PEP 723 script).

## Wiring agent-hook (Codex)

On macOS, Linux, and WSL, `just sync-agents x` also adds agent-hook guards to the Codex home (`~/.codex`).
The steps (lock, cleaning up change records, release, planning, and transactional updates) match Claude homes, with planning handled by `scripts/agent_hook_codex_plan.py`.
Codex records hook trust by position in `hooks.json` (event, group, and handler index).
Therefore, unlike Claude, registrations are not replaced.

- Groups that still match what the declaration wants are left in place. Codex continues to trust them.
- Only changed groups are emptied in place, and new groups are placed in an empty group with the same matcher (preferring a group of the same kind just emptied), or appended at the end if none exists. This applies equally when script fragments or agent-hook templates change.
- The three agent-hook guards (files-guard, secrets-guard, command-guard) are added alongside the scripts; rtk and formatter stay on scripts.
- If render's guards do not include exactly one of each of these three, treat it as if there is no release (keep existing guards if wired, and stop install).
- User-owned groups keep both their position and contents. Groups are never deleted.
- If a plan would violate these rules, that home stops (`stopped: placement: ...`).

Guards are added only when both Codex shells (the session shell and `$SHELL -lc`) are POSIX shells and pass agent-hook's sh invocation without extra output.
Otherwise, it falls back to `scripts` or `keep` just like when no release exists, and install stops. `just doctor` prints detailed shell status.
`just agent-hooks-uninstall x` empties guard groups in place (keeping their positions) and sets the marker.
`just agent-hooks-install x` puts guards back in the same positions, so Codex's trust records remain valid at those positions.
After install and uninstall, run the trust step (`scripts/codex_hooks_trust.py`) just like sync.
Because Codex runs only hooks whose hashes are trusted, earlier threads where guards were not yet trusted keep running the current scripts.

## Codex hooks

Codex reads `<codex home>/hooks.json`.
The block format matches Claude, matching `Bash` for shell tools and `Write|Edit` for apply_patch.
sync builds a Codex fragment from `.claude/settings.hooks.json` (`codex_fragment_from_claude`) and merges it under the same ownership rules as Claude's settings.json. It removes the block written by the rtk installer (`RETIRED_HOOK_COMMAND`).
The fragment rewrites only command: `block-*` guards go through `guard-codex.sh`, `-claude.` scripts swap for their `-codex.` counterparts, and everything else runs unchanged.
Do not place `.codex/hooks.json` in the repo. Codex also reads `.codex/hooks.json` in trusted projects, so placing it there causes hooks to run twice in this repo (detected by `just codex-hooks-trust --check` and doctor's `codex-hooks`).
Hook filenames control routing: `-claude.` goes only to Claude homes, and `-codex.` goes only to Codex.

Guards that block with exit 2 (`block-*.sh`) are invoked on Codex through `guard-codex.sh <guard>`.
Codex launches hooks in the session shell, which on Windows is `pwsh -Command`.
Because pwsh returns all non-zero exits as 1, exit 2 from a guard reaches Codex as a failed hook, and failed hooks pass through.
`guard-codex.sh` converts a guard's exit 2 and stderr into `permissionDecision: "deny"` on stdout.
Because every shell passes stdout through, blocking works across all OSes.
The guards themselves keep Claude's exit code contract unchanged.

Codex runs only hooks whose hashes are recorded as trusted (`hooks.state` in `~/.codex/config.toml`).
After syncing `~/.codex`, sync runs `scripts/codex_hooks_trust.py` to trust only hooks built from the fragment via Codex's app-server (`hooks/list` and `config/batchWrite`).
If a distributed hook file differs from its source by even 1 byte, it is not trusted.
When `hooks.json` has agent-hook groups, it also trusts only the exact commands for the three agent-hook guards (files-guard, secrets-guard, command-guard) emitted by the stable-path agent-hook via `render --harness codex --shell sh`.
If the stable path is missing or render fails, it skips trusting the guards and outputs WARN (scripts continue to run).
`just codex-hooks-trust --check` prints status without writing.
Each query to app-server waits up to 15 seconds, exiting 1 with WARN if there is no reply.
sync waits up to 120 seconds per step and kills the step's entire process group (including app-server) on timeout.
On Windows, it then runs `scripts/codex_sandbox_tools.py` so Codex's sandbox can execute mise tools such as rtk (`docs/runbook/windows-host.md`).
`just doctor` and `just status` include the same check.

## What sync does not distribute

**skill**: Both custom (hironow/skills) and third-party skills live in the `bunx skills` CLI store (`~/.agents/skills`), and git tracks only the declaration `dump/harness/skill-lock.json` (ADR 0043).
In each home's `skills/`, `just skills-place` creates relative symlinks to the store (or tracked copies if unsupported).
Use `-a universal` so the CLI writes only to the store without touching homes.
For same-named skills, hironow/skills takes precedence (checked by `just skills-lock-check` inside `just ci`).
Because declarations are public, `just dump-skills-lock` omits skills whose sources `gh` identifies as private. If any source's visibility cannot be verified, it fails without writing anything.

- `just dump-skills-lock`: Rebuild the declaration from the store (rejects changes that would drop hironow/skills entries)
- `just restore-skills-lock`: On a new machine, restore the store from the declaration and place into homes
- `just skills-update`: After merging hironow/skills, etc., update the store and place (`--only <name>` for a single skill)
- `just agent-bump`: Show current and latest versions of declared Claude plugin marketplaces, EGM, Pi packages, and skills. Run `just agent-bump <name> [version]` to bump or downgrade one and install it on this machine (ADR 0074). Declared items skip the 7-day wait. Run from a main checkout (refuses from a worktree). Uncommitted declarations do not stop it, so you can run it repeatedly and commit once (ADR 0075). Other machines run each installer after merge

**EGM**: Distributed not as ordinary store-managed skills, but as full plugins/packages including their references.
`sync-agents` distributes supplements to each home, while `just deploy` installs EGM itself with the same workflow as other plugins (for Claude Code and Pi from declarations; for Codex and Antigravity via `scripts/codex_agy_plugins.py` matching Pi's pin). There is no dedicated EGM install command.
Because this sync also distributes existing shared settings and hooks, check `just sync-agents-preview all` first.
Pi uses a pinned git package, and the existing installer places the same supplements and read-only reviewers.
In Pi's global context file, only content inside the EGM markers is managed; the rest of the body is left intact.
Do not install EGM skills separately via `bunx skills`.
Install order, precedence with local policies, and review isolation limits are in the [EGM runbook](runbook/egm.md).

**Claude Code plugins**: Settings fragments omit `enabledPlugins` and `extraKnownMarketplaces` (ADR 0037, because the plugin CLI rewrites them).
Plugins shared across all homes are declared in `dump/harness/claude-plugins.json`, and `just deploy` (`just claude-plugins-install` standalone) installs them into each home via the plugin CLI (ADR 0048, ADR 0056).
Marketplaces are pinned by tag, except untagged claude-plugins-official (tracks latest) and dotfiles's own hironow-plugins written as a repo-relative path (`./`).
The shared set holds only plugins that need no per-home configuration, and the script also flags plugins with un-defaulted configuration items as WARN in doctor (ADR 0057).
Because LSP plugins hold only the launch command name, commands are installed via mise (`config/mise/config.toml`). typescript-lsp works only where a workspace has TypeScript (up to 6.x) with `tsserver.js` in `node_modules` (TypeScript 7 lacks `tsserver.js`). The script collects LSP commands from each home's marketplace manifest and flags any in doctor as WARN if missing from PATH or unresponsive to a version query (default `--version`; `gopls version` for gopls).
In the declaration, `disabled` disables on every run and `retired` disables once per home per migration ID, recording completed migrations and schema read results in that home's `claude-plugins.sync-state.json` (written only during install).
sync does not modify these two keys.

**Antigravity CLI (`agy`) skills, settings, and MCP**: Antigravity manages skills itself via `antigravity plugin` (stored at `~/.gemini/config/plugins/<name>` in 1.5.5) and settings and MCP via `agy import` (`~/.gemini/antigravity-cli/settings.json` and `mcp/`) (ADR 0026).
Distributing these directly would bypass and overwrite its self-management, so dotfiles does not touch them.
Only the instruction layer (`~/.gemini/GEMINI.md`) is shared.
`~/.gemini/skills/` is a target for `skills-place`, but Antigravity reads from `plugins/`, so it is unused (and harmless).

## Running

```bash
just sync-agents            # ~/.claude only (default)
just sync-agents p a b      # Named homes only (p is ~/.claude)
just sync-agents all        # All agents
just sync-agents-preview …  # Preview diff without writing
```

Naming homes excludes the default `~/.claude`.
`just sync-agents a b` distributes only to `~/.claude-work-a` and `-b`, so include `p` or use `all` if `~/.claude` is also needed.
