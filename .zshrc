# load zgen
# !! zgen should be installed first !!
source "$HOME/.zgen/zgen.zsh"

# if the init script doesn't exist
# update should be `zgen selfupdate` and `zgen update`
if ! zgen saved; then
    echo "Creating a zgen save"
    
    zgen oh-my-zsh
    
    # plugins
    zgen oh-my-zsh plugins/git
    zgen oh-my-zsh plugins/sudo
    zgen oh-my-zsh plugins/golang
    zgen oh-my-zsh plugins/rust
    zgen oh-my-zsh plugins/command-not-found
    zgen load zsh-users/zsh-syntax-highlighting
    zgen load zsh-users/zsh-autosuggestions
    
    # bulk load
    zgen loadall <<EOPLUGINS
        zsh-users/zsh-history-substring-search
EOPLUGINS
    # ^ can't indent this EOPLUGINS
    
    # completions
    zgen load zsh-users/zsh-completions src
    
    # theme
    zgen load mafredri/zsh-async
    zgen load sindresorhus/pure
    
    # save all to init script
    zgen save
fi
# --- loaded zgen

# func
_cmd_exists() {
    command -v "$1" > /dev/null 2>&1
}

_file_exists() {
    [ -f $1 ]
}

_file_not_empty() {
    [ -s $1 ]
}

_cmd_success() {
    [ $? -eq 0 ]
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

# Precedence tweaks
# PNPM first for Node CLIs
export PNPM_HOME="$HOME/Library/pnpm"
path_prepend "$PNPM_HOME"

# Prefer OrbStack Docker if present
path_prepend "$HOME/.orbstack/bin"

export SPACESHIP_EXIT_CODE_SHOW=true

export EDITOR=vim
export GPG_TTY=$(tty)

# homebrew
if _cmd_exists brew; then 
    eval "$(brew shellenv)"
elif [ -x "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x "$HOME/.linuxbrew/bin/brew" ]; then
    eval "$("$HOME/.linuxbrew/bin/brew" shellenv)"
elif [ -x "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
fi

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

# k8s
if _cmd_exists kubectl; then source <(kubectl completion zsh); fi
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


# The following lines have been added by Docker Desktop to enable Docker CLI completions.
fpath=($HOME/.docker/completions $fpath)
autoload -Uz compinit
compinit
# End of Docker CLI completions

# Added by Antigravity
export PATH="$HOME/.antigravity/antigravity/bin:$PATH"
