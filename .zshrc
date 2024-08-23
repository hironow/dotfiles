# load zgen
source "${HOME}/.zgen/zgen.zsh"

# if the init script doesn't exist
if ! zgen saved; then
    echo "Creating a zgen save"
    
    zgen oh-my-zsh
    
    # plugins
    zgen oh-my-zsh plugins/git
    zgen oh-my-zsh plugins/sudo
    zgen oh-my-zsh plugins/pip
    zgen oh-my-zsh plugins/lein
    zgen oh-my-zsh plugins/golang
    zgen oh-my-zsh plugins/rust
    zgen oh-my-zsh plugins/gradle
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
    zgen load denysdovhan/spaceship-prompt spaceship
    
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

export SPACESHIP_EXIT_CODE_SHOW=true

export EDITOR=vim
export GPG_TTY=$(tty)

# local
export PATH=$PATH:/usr/local/bin

# homebrew
if _cmd_exists brew; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi

# Google Cloud SDK
if _file_exists "$HOME/google-cloud-sdk/path.zsh.inc"; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if _file_exists "$HOME/google-cloud-sdk/completion.zsh.inc"; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools

# wasmer
export WASMER_DIR="$HOME/.wasmer"
[ -s "$WASMER_DIR/wasmer.sh" ] && source "$WASMER_DIR/wasmer.sh"  # This loads wasmer

# k8s
if _cmd_exists kubectl; then source <(kubectl completion zsh); fi
# krew
export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"

# solana
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"

# java
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# terraform
autoload -U +X bashcompinit && bashcompinit
complete -o nospace -C /opt/homebrew/bin/terraform terraform

# go
export PATH="$HOME/go/bin:$PATH"

# docker desktop
if _file_exists "$HOME/.docker/init-zsh.sh"; then source "$HOME/.docker/init-zsh.sh"; fi

# github copilot cli
if _cmd_exists github-copilot-cli; then eval "$(github-copilot-cli alias -- "$0")"; fi

# curl
export PATH="/opt/homebrew/opt/curl/bin:$PATH"

# mise
if _cmd_exists mise; then 
    eval "$(~/.local/bin/mise activate zsh)"
    export PATH="$HOME/.local/share/mise/shims:$PATH"
fi

# poetry
export PATH="$HOME/.local/bin:$PATH"

# anaconda
# !! Contents within this block are managed by 'conda init' !!
CONDA_DIR=${CONDA_DIR:-"$HOME/anaconda3"}
__conda_setup=$("$CONDA_DIR/bin/conda" 'shell.zsh' 'hook' 2> /dev/null)
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if _file_exists "$HOME/anaconda3/etc/profile.d/conda.sh"; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    else
        export PATH="$HOME/anaconda3/bin:$PATH"
    fi
fi
unset __conda_setup

# bun completions
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

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

# terramate
complete -o nospace -C /opt/homebrew/bin/terramate terramate


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
alias relogin='exec $SHELL -l'
if _cmd_exists kubectl; then
    alias k="kubectl"
fi
if _cmd_exists mise; then
    alias x="mise x --"
fi
if _cmd_exists terramate; then
    alias t="terramate"
fi

