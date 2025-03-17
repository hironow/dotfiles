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

export SPACESHIP_EXIT_CODE_SHOW=true

export EDITOR=vim
export GPG_TTY=$(tty)

# local
export PATH=/usr/local/bin:$PATH
export PATH=$HOME/.local/bin:$PATH

# homebrew
eval "$(/opt/homebrew/bin/brew shellenv)"

# Google Cloud SDK
if _file_exists "$HOME/google-cloud-sdk/path.zsh.inc"; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if _file_exists "$HOME/google-cloud-sdk/completion.zsh.inc"; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$HOME/Library/Android/sdk/platform-tools:$PATH

# wasmer
export WASMER_DIR="$HOME/.wasmer"
# This loads wasmer
if _file_not_empty "$WASMER_DIR/wasmer.sh"; then source "$WASMER_DIR/wasmer.sh"; fi

# k8s
if _cmd_exists kubectl; then source <(kubectl completion zsh); fi
# krew
export PATH=${KREW_ROOT:-$HOME/.krew}/bin:$PATH

# java
export PATH=/opt/homebrew/opt/openjdk/bin:$PATH

# terraform
autoload -U +X bashcompinit && bashcompinit
complete -o nospace -C /opt/homebrew/bin/terraform terraform

# go
export PATH=$HOME/go/bin:$PATH

# docker desktop
if _file_exists "$HOME/.docker/init-zsh.sh"; then source "$HOME/.docker/init-zsh.sh"; fi

# github copilot cli
if _cmd_exists github-copilot-cli; then eval "$(github-copilot-cli alias -- "$0")"; fi

# curl
export PATH=/opt/homebrew/opt/curl/bin:$PATH

# mise
if _cmd_exists mise; then 
    eval "$(~/.local/bin/mise activate zsh)"
    # mise uses shims, so by adding mise's shims to the beginning of PATH, mise's commands are executed prefer
    export PATH=$HOME/.local/share/mise/shims:$PATH
fi

# cargo
source "$HOME/.cargo/env"

# ngrok
if _cmd_exists ngrok; then
    eval "$(ngrok completion)"
fi

# copilot cli
if _cmd_exists gh copilot; then
    eval "$(gh copilot alias -- zsh)"
fi

# crowdin
export PATH=/opt/homebrew/opt/crowdin@4/bin:$PATH

# terramate
complete -o nospace -C /opt/homebrew/bin/terramate terramate

# pnpm
export PNPM_HOME="$HOME/Library/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH=$PNPM_HOME:$PATH ;;
esac

# alias
# use tldr as help util
if _cmd_exists tldr; then
    alias help="tldr"
fi
# use tailscale
alias tailscale="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
# use rustdesk
alias rustdesk="/Applications/RustDesk.app/Contents/MacOS/rustdesk"

# shortcut
alias relogin='source ~/.zshrc'
if _cmd_exists kubectl; then
    alias k="kubectl"
fi
if _cmd_exists mise; then
    alias mx="mise exec --"
    alias mr="mise run"
fi
if _cmd_exists tofu; then
    alias t="tofu"
fi
if _cmd_exists terramate; then
    alias tm="terramate"
    alias tmr="terramate run --"
fi

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

# pnpm
export PNPM_HOME="$HOME/Library/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac

# flutter
export PATH=$HOME/flutter/bin:$PATH
export PATH=$HOME/.gem/bin:$PATH
export PATH=$HOME/Library/Android/sdk/cmdline-tools/latest/bin:$PATH

# Added by Windsurf
export PATH="$HOME/.codeium/windsurf/bin:$PATH"

# The following lines have been added by Docker Desktop to enable Docker CLI completions.
fpath=($HOME/.docker/completions $fpath)
autoload -Uz compinit
compinit
# End of Docker CLI completions

