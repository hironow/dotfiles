# Terminal keys: Ctrl+Enter through tmux and aligned word-movement keys

**Date:** 2026-10-02
**Status:** done (→ "Keybindings" and "Per-terminal settings" in [USAGE.md](../../USAGE.md)). Merged in [#457](https://github.com/hironow/dotfiles/pull/457) (main `9d9c9025`) and [#460](https://github.com/hironow/dotfiles/pull/460) (main `8b98bbcb`). Items 1-7 of "Items requiring physical-machine verification" (keystroke checks) have no recorded results. The tmux version is recorded in #460. Closed by owner instruction (2026-11-02, chat).
**Branch:** `feat/terminal-keys` (not yet created)
**Related:** PR #452 (initial Ctrl+Enter implementation; this change adds tmux support) / ADR 0022, 0024, 0031, 0033 (`$PROFILE` managed block; not used in this change)
**Blocking decisions:** none (confirmed with the user: add Ctrl+←/→ on Windows / macOS tmux is 3.2a or later)
**Graduates to:** `done(→ USAGE.md)` once stable. No new decision, so no ADR is created.

## Purpose

PR #452 made Ctrl+Enter insert a newline via Ghostty keybinds and a `.zshrc` zle widget, but **it does not work inside tmux**.
tmux `extended-keys` defaults to off and does not forward extended keys to applications that do not request them, so zsh in a pane cannot receive Ctrl+Enter in a distinguishable form.
How it drops depends on the version: 3.4 delivers nothing, while 3.7c falls back to a bare CR = Enter (F4-measured / F4-measured-2).
In addition, **word movement (one-word versions of ←/→) varies across terminals**.

This change aligns two behaviors:

1. Ctrl+Enter = newline (even inside tmux). **Target terminals are Ghostty and iTerm2** (terminals that can send extended keys from the terminal side).
   Terminal.app has no setting to send extended keys and is out of scope (F14).
   To work inside tmux, all three parties—terminal → tmux → application—must pass extended keys.
2. Word movement = one word left/right. Option+←/→ on macOS; Ctrl+←/→ on Windows and WSL.
   Word boundaries stay at zsh defaults. **The exact cursor landing position follows each implementation's default** (moving right differs between zsh and PSReadLine; F8).

## Confirmed facts (verified against primary sources)

**F1. zsh's default emacs keymap does not bind modified arrow keys.**
In zsh 5.9 `Src/Zle/zle_keymap.c`, `default_bindings()` adds **only bare cursor keys** via `add_cursor_key()` (it handles 3-character strings from terminfo and rejects candidates where `buf[3]` is non-empty).
`metabind[]` in `Src/Zle/zle_bindings.c` has `M-b` = `z_backwardword` / `M-f` = `z_forwardword`.
→ Currently zle cannot interpret `^[[1;3D` (Option+←, xterm form) or `^[[1;5D` (Ctrl+←), and echoes them as-is.

**F2. `xterm-keys` defaults to on in tmux 2.4 and later.** tmux CHANGES:
`* The xterm-keys option now defaults to on.` → Adding `setw -g xterm-keys on` is a no-op.
Adding it only invites confusion, so do not add it.

**F3. `extended-keys always` was added in tmux 3.2a (default is off).** CHANGES 3.2a:
`* Add an "always" value for the "extended-keys" option; if set then tmux will
forward extended keys to applications even if they do not request them.`
The user's macOS has 3.2a or later (confirmed; current Homebrew version is 3.5a).

**F4. According to the tmux 3.5 man page, `always` forces mode 1 output to panes.**
`When set to always, the client requests are ignored, and mode 1 output is forced.` /
`With respect to parent terminals, when set to on or always, the escape sequence to
enable extended keys is sent, if tmux knows that it is supported.` (merged PR #4038)
→ zsh does not request extended keys, so under this man page (3.5+), `on` receives no client request and leaves Ctrl+Enter as bare CR = same as Enter. **`always` is required**. (On 3.4, explicit `on` also delivered it = F4-measured. Do not rely on version-dependent behavior.)
(That PR's release announcement comment says "on/always requests mode 2 by default", which refers to the *request to the parent terminal*. For pane output mode, follow the man page above. Because the Windows host has no tmux, only static checks run here; actual measurements are recorded under F4-measured / F4-measured-2 below.)

**F4-measured (2026-10-02, tmux 3.4 on WSL, reproduced over 2 rounds using a PTY as the terminal)**: With the distributed conf (`always` + `xterm*:extkeys`), `ESC [13;5u` (CSI-u sent by Ghostty) arrives unchanged, and mode-1 `ESC [27;5;13~` is normalized to CSI-u (as expected in F5, 3.4 uses CSI-u).
**With default off (no `extended-keys` line), nothing arrives in the pane** (not CR; an unbound sequence `ESC [199~` passes through unchanged, so tmux recognizes it as an extended key and drops it).
When `on` or explicit `off` was set, it arrived in this environment (difference between unset default off and assigned `off` is likely specific to 3.4; since 3.7c's default was CR, the same difference is unlikely, though explicit `off` on 3.7c is unmeasured).
No side effects: bare Enter is `0d`, and `ESC [1;5D` (Ctrl+←) and `ESC b` (Option+←) are unchanged.
Source confirmation comes from `tty.c` (`ENEKS` is sent only when the option is non-zero), `input.c` (when `extended-keys == 2`, application mode requests are ignored), and 3.5a `options-table.c` (`extended-keys` defaults to `off`; `extended-keys-format` accepts `csi-u`/`xterm` and defaults to `xterm` = `default_num = 1`).
Physical macOS 3.7c verification is in F4-measured-2 below.

**F4-measured-2 (2026-10-02, tmux 3.7c on macOS, user review measurement; reproduced over 2 rounds with the same isolated socket + PTY method as #460)**: With the distributed conf, both CSI-u input `ESC [13;5u` and mode-1 input `ESC [27;5;13~` arrive in the pane as `ESC [27;5;13~`.
Instead of passing the input form through, tmux **forces mode 1 output**, matching F4's man page (`always` ignores client requests and forces mode 1 output; this measurement did not observe the "requests mode 2 from the parent terminal" behavior, which rests on CHANGES / man).
The result is identical with `always` alone (without the features line).
**With the default (no `extended-keys` line), it produces `0d` (bare CR) = indistinguishable from Enter.**
The boundary where this diverges from 3.4's "nothing arrives" is CHANGES 3.5: "Revamp extended keys support to more closely match xterm and support mode 2 as well as mode 1. This is a substantial change to key handling which changes tmux to always request mode 2 from parent terminal, changes to an unambiguous internal representation of keys" (key handling was overhauled in 3.5; 3.4 recognizes and drops it).
**The candidate boundary is 3.5**, based on CHANGES rather than exact boundary measurements (only 3.4 and 3.7c were measured; 3.5/3.5a/3.6 are unmeasured).
The control `ESC [199~` passes through unchanged on both versions (so it is not "dropped because unparseable").
No side effects: bare Enter `0d`, `ESC [1;5D`, and `ESC b` are unchanged.
Confirmed on the user's physical machine (3.7c), though we cannot claim "all 3.5+ versions". Only end-to-end testing with physical Ghostty keys remains undone (steps are in the checklist at the end).

**F5. `extended-keys-format` defaults to `xterm`, which reports C-S-a as `^[[27;6;65~`.**
man: `For example, C-S-a will be reported as '^[[27;6;65~' when set to xterm, and as
'^[[65;6u' when set to csi-u.` (modifiers = 1 + (1 shift / 2 alt / 4 ctrl))
→ With the default, Ctrl+Enter is `^[[27;5;13~`, which **PR #452 already binds in `.zshrc`**.
Leave `extended-keys-format` untouched (even if tmux 3.3/3.4 emits CSI-u, the same file handles `^[[13;5u`).

**F6. mode 1 converts only modified keys that lack a standard representation into extended form.**
→ `ESC b` / `ESC f` (= M-b / M-f) and `ESC [1;5D` (Ctrl+←) pass to the pane as legacy byte sequences.
Whether Ghostty pins Option+←/→ to `esc:b` / `esc:f` or passes Ctrl+←/→ through as-is, tmux does not re-encode them.

**F7. Ghostty's `esc:` keybind action sends an ESC-prefixed sequence.**
The official docs recommend `esc:` / `csi:` over `text:`, giving `esc:d` (= delete word right = M-d) as an example. The modifier `opt` is an alias for `alt`.
(ghostty.org/docs/config/keybind and Option Reference)

**F8. Verified at runtime on PSReadLine 2.3.6 (this host).**
Default bindings are `Ctrl+LeftArrow` → `BackwardWord` ("Move the cursor to the beginning of the current or previous word"), `Ctrl+RightArrow` → `NextWord` ("Move the cursor forward to the start of the next word"), `Ctrl+Backspace`/`Ctrl+w` → `BackwardKillWord`, and `Alt+d` → `KillWord`.
**Alt+arrow is unbound** (verified with `Get-PSReadLineKeyHandler`).
`Set-PSReadLineKeyHandler -Chord 'Alt+LeftArrow' -Function BackwardWord` succeeds, but does not persist to a file (`%APPDATA%\PSReadLine` is not created).

**Landing-position difference (decision)**: zsh `forward-word` moves to the end of the word (like emacs `M-f`), whereas PSReadLine `NextWord` moves to the start of the next word.
**Do not change Windows defaults**—do not overwrite working defaults via distributed files or break the user's muscle memory. Document the difference here.
If strict parity is ever wanted, add one line `Set-PSReadLineKeyHandler -Chord 'Ctrl+RightArrow' -Function ForwardWord` to the `$PROFILE` managed block (the existing pattern in deploy.sh / clean.sh / doctor.sh / tests applies; F13). Not doing that now.

**F9. By default, Windows Terminal uses Alt+←/→ to move pane focus and does not pass them to applications.**
microsoft/terminal generated `defaults.json` (`src/cascadia/TerminalSettingsModel/`):
`{ "keys": "alt+left", "id": "Terminal.MoveFocusLeft" }` / `alt+right` → `Terminal.MoveFocusRight` (same for `alt+up/down`; `alt+shift+arrows` is ResizePane).
This host's `settings.json` has only `actions: []` and three `keybindings` (ctrl+c / ctrl+v / alt+shift+d), **not overriding it** → WT consumes Alt+arrow.
**WT does not bind Ctrl+←/→** → they reach the application as-is (the WT Actions list has no Ctrl+arrow under moveFocus or resizePane).

**F10. macOS standard Terminal.app requires no configuration for Option+←/→ word movement.**
Apple's official shortcut list ("Edit a command line") lists `Move the insertion point forward one word | Option-Right Arrow` / `backward one word | Option-Left Arrow`, **without a "Use Option as Meta key" note** (that note appears on the `Option-D` = delete to end of word row).
→ There is no need to tell users to enable Meta for all Option keys (which changes Option+character composed input).

**F11. WSL needs no extra work.** `uname -s` = Linux enters deploy.sh's Unix branch and creates the same symlinks for `~/.zshrc` / `~/.tmux.conf` (the user confirmed their WSL shell is zsh).
`dump/macbook/Brewfile` installs tmux on macOS; Linux/WSL uses whatever version the user installed.

**F12. tmux config errors are non-fatal.** tmux(1):
`tmux shows any error messages from commands in configuration files in the first
session created, and continues to process the rest of the configuration file.`
→ On tmux older than 3.2a, the `extended-keys` line produces only a one-line warning and the rest of the config loads (the only impact is that Ctrl+Enter does not work).

**F13. An established pattern exists for PowerShell managed blocks** (append in deploy.sh → remove with `sed` in clean.sh → check markers in doctor.sh → `tests/unit/`, ADR 0022/0024/0031/0033).
**Not used** here (see F8 decision and rejected alternatives).

**F14. Terminal.app has no way to send extended keys.** Apple's "Change Profiles Keyboard settings" documents only the Key list (Add / Edit / Remove for function keys), "Use Option as Meta key", and "Scroll alternate screen", with no modifyOtherKeys / CSI-u output (nothing equivalent to iTerm2's "Send Hex Code").
→ Exclude Ctrl+Enter newline from Terminal.app scope, and confirm on a physical machine that it sends the **same raw byte (`0d`) as bare Enter** (if not, move it back to target terminals).

## Changes

### 1. `.zshrc` — Bind modified arrow keys

Added immediately after the ctrl+enter block (toward EOF).

```
# Word movement. zsh's default emacs keymap binds only bare cursor keys
# (Src/Zle/zle_keymap.c: add_cursor_key), so the xterm forms for
# modifier+arrow were unbound and echoed as garbage. Ghostty pins Option+arrow
# to ESC b/f (tools/ghostty-config), so the Alt form here is for iTerm2;
# Ctrl+arrow is what Windows Terminal leaves alone (its defaults claim
# alt+left/right for pane focus).
bindkey '^[[1;3D' backward-word # Option+left
bindkey '^[[1;3C' forward-word  # Option+right
bindkey '^[[1;5D' backward-word # Ctrl+left
bindkey '^[[1;5C' forward-word  # Ctrl+right
```

- Adding Ctrl+←/→ was the user's choice (keys WT does not intercept on Windows/WSL).
  Because macOS and WSL share `.zshrc`, Ctrl+←/→ also works on macOS (consistent).
- Do not bind Shift+←/→ (selection). Do not add `select-word-style` (keep zsh default word boundaries).

### 2. `tools/ghostty-config` — Explicitly pin Option+←/→

Added to the Keybind section (leave existing ctrl+enter line unchanged).

```
# Option+left/right: one word left/right (the docs' esc: example is esc:d =
# M-d). `esc:` sends an ESC-prefixed sequence and opt is an alias for alt;
# ESC b / ESC f are zsh's built-in backward-word / forward-word, so this keeps
# working inside tmux (see tools/tmux/tmux.conf).
keybind = opt+left=esc:b
keybind = opt+right=esc:f
```

### 3. `tools/tmux/tmux.conf` — Enable extended keys

Added immediately after the TrueColor block (leave existing lines unchanged).

```
# Extended keys (modifyOtherKeys): Ctrl+Enter inside a pane. The shipped file
# (tools/tmux/tmux.conf) carries the measured rationale; this block is only the
# spec for the two commands.
set -s extended-keys always
# tmux only asks the outer terminal for extended keys when it knows it is
# supported; this is the tmux wiki's Modifier-Keys line. Terminals that ignore
# the request are unaffected (tmux recognises extended keys regardless).
set -as terminal-features 'xterm*:extkeys'
```

### 4. `USAGE.md` — Add to the "Key operations" table

| Key | Behavior |
| --- | --- |
| `Ctrl+Enter` | Insert newline (does not submit; works on Ghostty / iTerm2, including inside tmux) |
| `Option+←` / `Option+→` | Move backward / forward one word |
| `Ctrl+←` / `Ctrl+→` | Move backward / forward one word (use this on Windows and WSL because Windows Terminal claims Alt+arrow) |

Two lines right after the table:

- `Ctrl+Enter` inside tmux requires tmux 3.2a or later (check with `tmux -V`; older versions show a warning and everything else works).
- Word boundaries and stopping positions stay at zsh defaults (Windows PowerShell uses PSReadLine defaults, so `Ctrl+→` lands slightly differently than in zsh; see `docs/plan/terminal-keys.md` for terminal differences).

Because `USAGE.md` covers "how to use zsh", do not expand non-shell topics (PowerShell / Windows Terminal) beyond this table note.

### 5. `docs/plan/terminal-keys.md`

This document. Put the "GUI steps" and "Verification" sections at the end.

### 6. Do not modify `README.md`

Deploy behavior does not change (see F8 decision and rejected alternatives for not adding a PSReadLine block). This resolves review comment 5's request to update README.

### 7. `tests/unit/test_terminal_word_movement.py` (new, static check)

Runs even on hosts without tmux / zsh / Ghostty binaries (native Windows).

- `.zshrc`: check that **each** of the four sequences `^[[1;3D` / `^[[1;3C` / `^[[1;5D` / `^[[1;5C` has exactly one `bindkey '<seq>' <widget>` line (widget is `backward-word` / `forward-word`).
  Do not count the two existing Ctrl+Enter `bindkey` lines or other `bindkey` lines (counting all `bindkey` lines would collide with PR #452's lines).
  Also verify that `^[[1;2` / `^[[1;4` (Shift variants) are absent.
- `tools/ghostty-config`: `keybind = opt+left=esc:b` and `keybind = opt+right=esc:f` appear once each.
- `tools/tmux/tmux.conf`: on non-comment command lines (**excluding comment lines**), `set -s extended-keys always` and `terminal-features` with `extkeys` appear once each, and `xterm-keys` and `extended-keys-format` lines are **absent** (comments legitimately mention `xterm-keys`, so do not use raw substring search).
  Also verify that `3.2a` appears in comments (locking the explicit prerequisite into the artifact).
- Existing `tests/unit/test_zshrc_ctrl_enter.py` checks that PR #452's ctrl+enter block remains intact.

## GUI steps (parts the repository cannot distribute)

### Terminal.app

- No extra setup required (F10; Option+←/→ moves by word by default).
- Ctrl+Enter newline is out of scope (F14). Confirm on a physical machine that it remains CR.

### iTerm2 (if used)

- In Profiles → Keys, assign "Send Escape Sequence" to ⌥← / ⌥→ sending `b` / `f` respectively (default output varies by environment, so set it explicitly rather than relying on terminal defaults).
- To make Ctrl+Enter insert a newline, assign "Send Hex Code" in the same Keys tab to `^⏎` sending `0x1b 0x5b 0x32 0x37 0x3b 0x35 0x3b 0x31 0x33 0x7e` (= `^[[27;5;13~`, which `.zshrc` already binds).

### Windows (Windows Terminal + PowerShell / WSL)

- No extra setup required. WT does not bind Ctrl+←/→, so they pass through; PowerShell uses PSReadLine defaults for word movement, and WSL zsh uses this change's `.zshrc` (F8, F9).
- Only if you also want Alt+←/→ on Windows, unbind `alt+left` / `alt+right` in WT Actions and add two PSReadLine lines to `$PROFILE`. **Not doing this now** (do not automate).

## Verification

### Verified on this host (native Windows)

- F8: Executed in pwsh to confirm PSReadLine default bindings and that adding Alt+arrow works (read back with `Get-PSReadLineKeyHandler`).
- F9: Fetched Windows Terminal's `defaults.json`, confirmed `alt+left/right` → `Terminal.MoveFocusLeft/Right`, and verified this host's `settings.json` has no overrides.
- Post-change self-test: run **`just check` (completion gate required by ROOT_AGENTS)** and also `just ci` including unit tests. Check markdown files standalone with `markdownlint-cli2` first.

### Items requiring physical-machine verification (macOS / tmux / each terminal) — pre-merge gate

1. `tmux -V` is 3.2a or later (confirmed; record measured version in the PR body).
2. `cat -v` in a pane inside tmux:
   Option+← → `^[b`, Ctrl+← → `^[1;5D`, Ctrl+Enter → `^[[27;5;13~`.
   Also at the zsh prompt, Ctrl+Enter **inserts a newline without submitting** (type `ls`, press Ctrl+Enter → does not execute yet). This is the true acceptance condition.
3. `cat -v` outside tmux (Ghostty): Option+← → `^[b` (keybind fires).
4. tmux config values: `tmux show -s extended-keys` → `always`, `tmux show -s terminal-features | tr ',' '\n' | grep extkeys`.
5. `cat -v` in Terminal.app (inside and outside tmux): Option+← moves by word (either `^[b` or handled by the terminal). For Ctrl+Enter, **no sequence starting with `^[` appears** (check raw bytes below to confirm it is `0d`, identical to `Enter`). This finalizes F14.
6. If using iTerm2 (inside and outside tmux): ⌥← → `^[b`, Ctrl+Enter → `^[[27;5;13~`.
7. Current state of "Use Option as Meta key" (if also using Terminal.app). By F10, Option+←/→ should work even when disabled.

### How to read raw bytes (using raw mode only to distinguish Ctrl+Enter from Enter)

Because `cat -v` runs in cooked tty mode, **CR is translated to NL by ICRNL and disappears** (bare Enter and unsupported Ctrl+Enter look like the same newline).
Sequences starting with ESC are not translated and show up in `cat -v`, whereas raw mode is needed to tell whether a key emits `0d`.

```bash
# Read only 1 byte and return immediately (does not hang)
stty raw -echo; dd bs=1 count=1 2>/dev/null | od -An -tx1; stty sane
```

- Bare Enter / Ctrl+Enter without extended-key support (directly in terminal) → `0d` (such as Terminal.app in F14)
- Ctrl+Enter with extended-key support → `1b` (ESC; remaining bytes stay on the prompt, clear with `Ctrl+U`)
- **Inside tmux is different**: default off (no `extended-keys` line) **varies by version**—tmux 3.4 delivers nothing (not `0d`), while 3.7c delivers `0d` (= same as Enter). Because `dd` waits when nothing arrives, press regular Enter or `Ctrl+C` to read 1 byte and return (`Ctrl+C` does not trigger SIGINT during `stty raw` and arrives as 1 byte).

In short, **"Ctrl+Enter outputs `0d`" = indistinguishable from Enter**, and seeing `^M` is not expected (if seen, ICRNL is off, a different state).
To inspect raw bytes reliably, run outside tmux (directly in the terminal); inside tmux, behavior differs by version as noted above (3.4 emits nothing, 3.7c emits `0d`).

**If the F4 mode 1 reading is wrong** (Option+← arrives in another form such as `^[[27;3;68~`), append that form to `.zshrc`. Dropping to `extended-keys on` is an alternative, but we reject it because Ctrl+Enter would stop working.

**Merge policy:**

- Include these 7 items as a checklist in the PR body (do not claim "it works" before verifying).
- **Agents do not merge.** Stop after opening the PR and wait for user and reviewer review. Do not squash merge until instructed, even if all CI checks are green.

## Rejected alternatives

| Option | Reason rejected |
|---|---|
| Add a PSReadLine Alt+←/→ block to `$PROFILE` | F9. WT uses alt+left/right for pane navigation, so they never reach PSReadLine. Ctrl+←/→, which WT does not bind, **already works by default** (F8), so doing nothing on Windows is right |
| Override `Ctrl+RightArrow` to `ForwardWord` in `$PROFILE` to match landing position | Do not overwrite working Windows defaults via distributed files (F8 decision). If needed later, it can be added as 1 line + existing managed block pattern (F13) |
| Manage WT's `settings.json` in the repo to write `unbound` | GUI-managed JSONC file full of GUIDs; cannot use the same marker pattern as other configs. Keep it as documented manual steps |
| Add `setw -g xterm-keys on` | F2. No-op and misleading |
| Use `extended-keys on` | F4 (3.5+ man page). zsh does not request them, so Ctrl+Enter stays bare CR |
| Change `extended-keys-format` to `csi-u` | F5. Default xterm `^[[27;5;13~` is already bound in `.zshrc`. Zero benefit and untestable risk |
| Set `default-terminal` to `tmux-256color` | Unrelated to this goal. Only adds missing-terminfo risk |
| Branch by version with `%if` / check tmux version in doctor | By F12, tmux < 3.2a only emits a one-line warning and disables the feature. `%if` is only parsed in tmux 2.4+ and comparison format operators are version-dependent, so trying to protect old tmux introduces new breakage. State the prerequisite explicitly in comments and USAGE.md |
| Advise enabling Terminal.app's "Use Option as Meta key" | F10. Apple's official docs list Option+←/→ for word movement without the Meta note. No need to recommend making all Option keys Meta |
| Also target Terminal.app for Ctrl+Enter | F14. Terminal.app has no way to send extended keys. Confirm in physical-machine check 5 |
| Rewrite Ghostty's existing ctrl+enter line to `csi:13;5u` | Identical bytes. No value in touching a merged line already verified on a physical machine |
| Add a `just terminal-keys-probe` recipe | Physical-machine verification requires a human pressing keys while watching `cat -v` and cannot be automated. Simply list the commands (`cat -v`, `tmux show -s …`) here |
| Omit Ctrl+←/→ as "unnecessary on macOS" | By F1, it is unbound on Windows/WSL. WT does not capture it, and the user chose it |
| Create a standalone runbook instead of `docs/plan/` | Duplicates plan and procedure. Consolidate into this document |

## Risks and mitigations

- **If F4 (mode 1) is wrong, Option+← garbles inside tmux.**
  → Takes 5 seconds to check in physical-machine check 2. Handling for an alternate sequence is also ready.
- **`terminal-features 'xterm*:extkeys'` affects terminals without modifyOtherKeys support.**
  → tmux only sends the request; terminals that ignore it keep sending legacy sequences. tmux itself always recognizes extended keys (F4). Also the upstream wiki's recommended line.
- **Warning appears on tmux older than 3.2a.** → Non-fatal by F12. State the prerequisite in comments and USAGE.md.
- **Ctrl+Enter only works on Ghostty / iTerm2.** → The goal is scoped there, so do not claim "newline everywhere". List the terminal names in the USAGE.md table too.
- **Ghostty `opt+left=esc:b` collides with an existing keybind.** → The test checks "once each", catching duplicate definitions.
