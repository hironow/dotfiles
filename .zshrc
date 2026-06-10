# Helper functions
_cmd_exists() {
    command -v "$1" > /dev/null 2>&1
}

_file_exists() {
    [ -f $1 ]
}

_file_not_empty() {
    [ -s $1 ]
}

path_has() {
    case ":$PATH:" in
        *":$1:"*) return 0 ;;
        *) return 1 ;;
    esac
}

path_prepend() {
    if [ -n "$1" ] && ! path_has "$1"; then
        PATH="$1:$PATH"
    fi
}

# Homebrew (kept early so brew-provided tools land on PATH up front).
# NOTE: sheldon/starship init moved to EOF (after `mise activate`) because
# they are mise-provisioned now; guarding them here — before mise is on
# PATH — silently skipped prompt + plugins on WSL where there is no brew.
if [ -x "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x "$HOME/.linuxbrew/bin/brew" ]; then
    eval "$("$HOME/.linuxbrew/bin/brew" shellenv)"
elif [ -x "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
fi

# zsh-autosuggestions performance settings
ZSH_AUTOSUGGEST_MANUAL_REBIND=1
ZSH_AUTOSUGGEST_BUFFER_MAX_SIZE=20
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# Precedence tweaks
# pnpm is provided per-repo by corepack; we do NOT install pnpm globals.
# Keep PNPM_HOME so the content-addressed store stays at ~/Library/pnpm/store
# (shared by per-project `pnpm install`), but deliberately do NOT put the
# global bin dir on PATH — that makes `pnpm add -g` abort, steering global
# CLIs to mise's npm: backend instead.
# See docs/adr/0017-retire-pnpm-global-for-corepack.md.
export PNPM_HOME="$HOME/Library/pnpm"

# Prefer OrbStack Docker if present
path_prepend "$HOME/.orbstack/bin"

# Editor
export EDITOR=vim
# GPG agent support
export GPG_TTY=$(tty)

# Google Cloud SDK
# Source path setup only if PATH does not already contain the SDK bin to avoid duplicates
if _file_exists "$HOME/google-cloud-sdk/path.zsh.inc"; then
    if ! path_has "$HOME/google-cloud-sdk/bin"; then
        source "$HOME/google-cloud-sdk/path.zsh.inc"
    fi
fi
if _file_exists "$HOME/google-cloud-sdk/completion.zsh.inc"; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
path_prepend "$HOME/Library/Android/sdk/platform-tools"

# wasmer
export WASMER_DIR="$HOME/.wasmer"
# This loads wasmer
if _file_not_empty "$WASMER_DIR/wasmer.sh"; then source "$WASMER_DIR/wasmer.sh"; fi

# k8s (cached completion for speed)
if _cmd_exists kubectl; then
    _kubectl_comp_cache="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/kubectl_completion.zsh"
    if [[ ! -f "$_kubectl_comp_cache" || ! -s "$_kubectl_comp_cache" ]]; then
        mkdir -p "${_kubectl_comp_cache:h}"
        kubectl completion zsh > "$_kubectl_comp_cache"
    fi
    source "$_kubectl_comp_cache"
    unset _kubectl_comp_cache
fi
# krew
path_prepend "${KREW_ROOT:-$HOME/.krew}/bin"

# java
path_prepend "/opt/homebrew/opt/openjdk/bin"



# go
path_prepend "$HOME/go/bin"

# curl
path_prepend "/opt/homebrew/opt/curl/bin"

# cargo
if _file_exists "$HOME/.cargo/env"; then
    source "$HOME/.cargo/env"
fi

# bun
path_prepend "$HOME/.bun/bin"

# local
path_prepend "/usr/local/bin"
path_prepend "$HOME/.local/bin"

# mise activate is intentionally NOT here — it lives at EOF so its
# chpwd/precmd hook runs after every later PATH edit (vite-plus,
# antigravity, dbt, ...) and mise-managed tool dirs end up first in
# PATH. See ADR 0023.


# alias
# use tldr as help util
if _cmd_exists tldr; then
    alias help="tldr"
fi
# use tailscale
alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

# shortcut
alias relogin='source ~/.zshrc'
if _cmd_exists kubectl; then
    alias k="kubectl"
fi
if _cmd_exists mise; then
    alias mx="mise exec --"
    alias mr="mise run"
fi
if _cmd_exists just; then
    alias j="just"
fi
# tofu / terramate aliases are defined at EOF (after `mise activate`),
# because tofu is mise-provisioned (opentofu) and only lands on PATH once
# activate runs. Guarding here — before activate — silently skipped `t` on
# WSL where there is no Homebrew. See the post-activate alias block at EOF.


# Claude Code
# Each cc* alias is the runner-specific launcher per dotfiles ADR 0012
# Path D: prepend RUNOPS_ACTOR_TYPE=ai-agent so any 5-tool CLI invoked
# from inside Claude Code sees the correct caller classification
# (gateway ADR 0035 architectural pin). The env is set in alias scope
# only (= context-specific override), so a parent shell value is never
# inherited and the runbook-only "local human-operator direct" path
# stays uncontaminated.
alias cc='RUNOPS_ACTOR_TYPE=ai-agent ~/.local/bin/claude'
alias cc-p='RUNOPS_ACTOR_TYPE=ai-agent CLAUDE_CONFIG_DIR=~/.claude ~/.local/bin/claude'
alias cc-a='RUNOPS_ACTOR_TYPE=ai-agent CLAUDE_CONFIG_DIR=~/.claude-work-a ~/.local/bin/claude'
alias cc-b='RUNOPS_ACTOR_TYPE=ai-agent CLAUDE_CONFIG_DIR=~/.claude-work-b ~/.local/bin/claude'
alias cc-c='RUNOPS_ACTOR_TYPE=ai-agent CLAUDE_CONFIG_DIR=~/.claude-work-c ~/.local/bin/claude'
alias cc-d='RUNOPS_ACTOR_TYPE=ai-agent CLAUDE_CONFIG_DIR=~/.claude-work-d ~/.local/bin/claude'

# eza-backed `ls`/`ll` aliases are defined at EOF (after `mise activate`),
# because eza is provisioned by mise and only lands on PATH once activate
# runs. Guarding the alias here — before activate — would always see eza
# absent and silently skip it. See the eza block at the bottom of this file.

# Git worktree navigation
wgo() {
    eval $(git wgo "$@")
}

# history settings
export HISTFILE=~/.zsh_history
export HISTSIZE=10000
export SAVEHIST=10000
export HISTFILESIZE=10000
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_SAVE_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt INC_APPEND_HISTORY
setopt HIST_EXPIRE_DUPS_FIRST


# Completion system (optimized - only regenerate cache once per day)
fpath=($HOME/.docker/completions $fpath)
autoload -Uz compinit
_comp_files=(${ZDOTDIR:-$HOME}/.zcompdump(Nm-20))
if (( $#_comp_files )); then
    compinit -C
else
    compinit
fi
unset _comp_files
# Compile zcompdump in background for faster loading
{
    if [[ -s "${ZDOTDIR:-$HOME}/.zcompdump" && (! -s "${ZDOTDIR:-$HOME}/.zcompdump.zwc" || "${ZDOTDIR:-$HOME}/.zcompdump" -nt "${ZDOTDIR:-$HOME}/.zcompdump.zwc") ]]; then
        zcompile "${ZDOTDIR:-$HOME}/.zcompdump"
    fi
} &!

# fzf-tab (must be loaded after compinit)
[[ -f ~/.local/share/fzf-tab/fzf-tab.plugin.zsh ]] && source ~/.local/share/fzf-tab/fzf-tab.plugin.zsh
# fzf-tab config: preview with ls
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls -1 --color=always $realpath'
zstyle ':fzf-tab:*' switch-group '<' '>'

# fzf keybindings/completion (Ctrl-R) are initialized at EOF (after
# `mise activate` + compinit) because fzf is mise-provisioned now; the old
# pre-activate position silently skipped it on WSL (no Homebrew). See EOF.

# Added by Antigravity (dedup so a re-source / installer re-run cannot double it)
path_prepend "$HOME/.antigravity/antigravity/bin"


# Vite+ bin (https://viteplus.dev)
if _file_exists "$HOME/.vite-plus/env"; then
    . "$HOME/.vite-plus/env"
fi

# guard for Python package index
# see: https://shisho.dev/docs/ja/r/202603-takumi-guard-pypi/

# --- Security Hardening (Added by script) ---
# Enforce Flatt Security's PyPI Proxy for pip
export PIP_INDEX_URL="https://pypi.flatt.tech/simple/"

# Use uv for python packages where possible
alias pip='uv pip'
# --- End Security ---

# Added by dbt Fusion extension (ensure dbt binary dir on PATH)
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    export PATH="$HOME/.local/bin:$PATH"
fi
# Added by dbt Fusion extension
alias dbtf="$HOME/.local/bin/dbt"

# CF CLI completions
[[ -f "$HOME/.config/cf/completions/_cf.zsh" ]] && source "$HOME/.config/cf/completions/_cf.zsh"

# ant (Anthropic CLI) completion — cached, regenerated only when missing
if _cmd_exists ant; then
    _ant_comp_cache="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/ant_completion.zsh"
    if [[ ! -f "$_ant_comp_cache" || ! -s "$_ant_comp_cache" ]]; then
        mkdir -p "${_ant_comp_cache:h}"
        ant @completion zsh > "$_ant_comp_cache"
    fi
    source "$_ant_comp_cache"
    unset _ant_comp_cache
fi

# Antigravity CLI (installs into ~/.local/bin, already on PATH via line ~119;
# use the dedup helper so a re-run of the installer cannot double-register it)
path_prepend "$HOME/.local/bin"

# mise (run LAST so its chpwd/precmd hook prepends mise tool dirs after
# every late PATH edit above — vite-plus, antigravity, dbt Fusion,
# etc. — and mise-managed versions end up first in PATH per
# `mise doctor`. Shims are intentionally NOT on PATH (interactive shells
# use activate only; cron/IDE/non-shell consumers should use
# `mise exec --` or shims in ~/.zshenv). See ADR 0023.
if _cmd_exists mise; then
    eval "$(mise activate zsh)"
fi

# Sheldon (plugin manager) + Starship (prompt) — initialized here, AFTER
# `mise activate`, because both are mise-provisioned (declared in
# config/mise/config.toml) and only land on PATH once activate runs. The
# old position (before activate) relied on Homebrew supplying them early,
# which silently skipped both on WSL where there is no brew. Guarded so a
# host missing either tool still gets a working (plain) shell.
if _cmd_exists sheldon; then
    eval "$(sheldon source)"
fi
if _cmd_exists starship; then
    eval "$(starship init zsh)"
fi

# tofu / terramate aliases — tofu is mise-provisioned (opentofu) so it is
# only on PATH after activate; defining `t` here keeps it from being
# silently skipped on WSL. Still guarded so a host without the tool is fine.
if _cmd_exists tofu; then
    alias t="tofu"
fi
if _cmd_exists terramate; then
    alias tm="terramate"
    alias tmr="terramate run --"
fi

# >>> grok installer >>>
path_prepend "$HOME/.grok/bin"
fpath=(~/.grok/completions/zsh $fpath)
autoload -Uz compinit && compinit -C
# <<< grok installer <<<

# fzf keybindings and completion (Ctrl-R) — cached. Defined here, after
# `mise activate` + the compinit above, because fzf is mise-provisioned now;
# the old pre-activate position silently skipped it on WSL (no Homebrew).
if _cmd_exists fzf; then
    _fzf_cache="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/fzf_init.zsh"
    if [[ ! -f "$_fzf_cache" ]]; then
        mkdir -p "${_fzf_cache:h}"
        fzf --zsh > "$_fzf_cache"
    fi
    source "$_fzf_cache"
    unset _fzf_cache
fi

# eza for ls replacement (defined here, after `mise activate`, so eza is
# already on PATH). Guarded so a host without eza falls back to the system
# `ls` instead of erroring with "command not found: eza" on every call.
if _cmd_exists eza; then
    alias ls='eza --icons --git'
    alias ll='eza -al --icons --git'
fi
