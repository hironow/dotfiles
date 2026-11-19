# Using zsh

A fish-like zsh setup using Sheldon and Starship (Mac, Linux, and WSL).

## Setup

On Linux and WSL, install zsh first and set it as your login shell (macOS uses zsh by default).
Because `install.sh` never uses sudo, it only prints install instructions if zsh is missing (`just doctor` reports this as well).

```bash
sudo apt-get install -y zsh && chsh -s "$(command -v zsh)"   # Linux and WSL only
```

Open a new terminal, then run the following (mise installs sheldon):

```bash
just deploy   # Deploy configuration
sheldon lock  # First time only: install plugins
```

## Keybindings

| Key | Action |
| --- | --- |
| `Ctrl+R` | Fuzzy-search command history (fzf) |
| `Tab` | Fuzzy-complete with preview (fzf-tab) |
| `<` / `>` | Switch fzf-tab completion groups |
| `Ctrl+Enter` | Insert a newline without submitting (works in Ghostty and iTerm2, including inside tmux) |
| `Option+←` / `Option+→` | Move backward / forward one word |
| `Ctrl+←` / `Ctrl+→` | Move backward / forward one word (for Windows and WSL, since Windows Terminal uses Alt+arrow keys) |

`Ctrl+Enter` inside tmux requires tmux 3.2a or later (check with `tmux -V`; older versions only print a warning and everything else works). Word boundaries and stop positions keep zsh defaults; Windows PowerShell uses PSReadLine defaults, so `Ctrl+→` lands slightly differently.

Per-terminal settings:

- Ghostty: No configuration needed (`tools/ghostty-config` binds `Option+←` / `Option+→` to word movement).
- Terminal.app: `Option+←` / `Option+→` move by word out of the box. It cannot send extended keys, so `Ctrl+Enter` newline does not work.
- iTerm2: In Profiles → Keys, bind `⌥←` / `⌥→` to "Send Escape Sequence" `b` / `f`. To make `Ctrl+Enter` insert a newline, bind `^⏎` to "Send Hex Code" `0x1b 0x5b 0x32 0x37 0x3b 0x35 0x3b 0x31 0x33 0x7e` (`^[[27;5;13~`).
- Windows Terminal (PowerShell and WSL): No configuration needed. Windows Terminal uses `Alt+←` / `Alt+→` to switch panes, so use `Ctrl+←` / `Ctrl+→` instead.

## Aliases and functions

| Name | Expands to |
| --- | --- |
| `k` | `kubectl` |
| `j` | `just` |
| `mx` | `mise exec --` |
| `mr` | `mise run` |
| `cc` | `RUNOPS_ACTOR_TYPE=ai-agent claude` |
| `j-cc` / `j-pi` | Choose a thinking level with Jev and launch Claude Code / Pi ([guide](docs/runbook/jev-launchers.md)) |

## Caches

These caches speed up startup.
After updating tools, clear them with `just clean-cache` and re-run `sheldon lock` (`just clean-all` also removes deployed configs).

| Cache | Purpose |
| --- | --- |
| `~/.cache/zsh/kubectl_completion.zsh` | kubectl completions |
| `~/.cache/zsh/fzf_init.zsh` | fzf keybindings and completions |
| `~/.zcompdump*` | zsh completions |
| `~/.local/share/sheldon/` | Sheldon plugins |
| `~/.local/share/fzf-tab/` | fzf-tab |

## Startup time

Target is under 300ms.

```bash
time zsh -i -c exit
```
