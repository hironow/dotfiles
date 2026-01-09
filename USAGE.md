# Zsh Configuration Usage

Fish-like zsh setup with Sheldon + Starship.

## Quick Start

```bash
# Deploy dotfiles
just deploy

# Install plugins (first time only)
sheldon lock
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Fuzzy search command history (fzf) |
| `ESC ESC` | Add sudo to current command |
| `Tab` | Fuzzy completion with preview (fzf-tab) |
| `<` / `>` | Switch completion groups in fzf-tab |

## Commands

### Aliases

| Alias | Command |
|-------|---------|
| `k` | `kubectl` |
| `j` | `just` |
| `mx` | `mise exec --` |
| `mr` | `mise run` |
| `cc` | Claude Code |

## Maintenance

```bash
# Rebuild caches (after updating tools)
just clean-cache
sheldon lock

# Full cleanup
just clean-all
```

## Cache Files

The following caches are created for faster startup:

| Cache | Purpose |
|-------|---------|
| `~/.cache/zsh/kubectl_completion.zsh` | kubectl completion |
| `~/.cache/zsh/fzf_init.zsh` | fzf keybindings |
| `~/.zcompdump*` | zsh completion cache |
| `~/.local/share/sheldon/` | Sheldon plugins |
| `~/.local/share/fzf-tab/` | fzf-tab plugin |

Use `just clean-cache` to remove all caches.

## Startup Time

Target: < 300ms

```bash
# Measure startup time
time zsh -i -c exit
```
