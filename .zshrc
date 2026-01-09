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

# Homebrew (must be early for sheldon/starship)
if [ -x "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x "$HOME/.linuxbrew/bin/brew" ]; then
    eval "$("$HOME/.linuxbrew/bin/brew" shellenv)"
elif [ -x "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
fi

# Sheldon (plugin manager)
if _cmd_exists sheldon; then
    eval "$(sheldon source)"
fi

# Starship (prompt)
if _cmd_exists starship; then
    eval "$(starship init zsh)"
fi

# zsh-autosuggestions performance settings
ZSH_AUTOSUGGEST_MANUAL_REBIND=1
ZSH_AUTOSUGGEST_BUFFER_MAX_SIZE=20
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# Precedence tweaks
# PNPM first for Node CLIs
export PNPM_HOME="$HOME/Library/pnpm"
path_prepend "$PNPM_HOME"

# Prefer OrbStack Docker if present
path_prepend "$HOME/.orbstack/bin"

export EDITOR=vim
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
source "$HOME/.cargo/env"

# bun
path_prepend "$HOME/.bun/bin"

# local
path_prepend "/usr/local/bin"
path_prepend "$HOME/.local/bin"

# mise
if _cmd_exists mise; then 
    eval "$(mise activate zsh)"
fi


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
if _cmd_exists tofu; then
    alias t="tofu"
fi
if _cmd_exists terramate; then
    alias tm="terramate"
    alias tmr="terramate run --"
fi


# Claude Code
alias cc='~/.local/bin/claude'
alias cc-p='CLAUDE_CONFIG_DIR=~/.claude ~/.local/bin/claude'
alias cc-w='CLAUDE_CONFIG_DIR=~/.claude-work-c ~/.local/bin/claude'


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

# fzf keybindings and completion (Ctrl+R for history search) - cached
if _cmd_exists fzf; then
    _fzf_cache="${XDG_CACHE_HOME:-$HOME/.cache}/zsh/fzf_init.zsh"
    if [[ ! -f "$_fzf_cache" ]]; then
        mkdir -p "${_fzf_cache:h}"
        fzf --zsh > "$_fzf_cache"
    fi
    source "$_fzf_cache"
    unset _fzf_cache
fi

# Added by Antigravity
export PATH="$HOME/.antigravity/antigravity/bin:$PATH"
