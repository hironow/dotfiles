# load zgen
# !! zgen should be installed first !!
source "$HOME/.zgen/zgen.zsh"

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
export PATH=$PATH:/usr/local/bin
export PATH=$PATH:$HOME/.local/bin

# homebrew
eval "$(/opt/homebrew/bin/brew shellenv)"

# Google Cloud SDK
if _file_exists "$HOME/google-cloud-sdk/path.zsh.inc"; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if _file_exists "$HOME/google-cloud-sdk/completion.zsh.inc"; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools

# wasmer
export WASMER_DIR="$HOME/.wasmer"
# This loads wasmer
if _file_not_empty "$WASMER_DIR/wasmer.sh"; then source "$WASMER_DIR/wasmer.sh"; fi

# k8s
if _cmd_exists kubectl; then source <(kubectl completion zsh); fi
# krew
export PATH=$PATH:${KREW_ROOT:-$HOME/.krew}/bin

# java
export PATH=$PATH:/opt/homebrew/opt/openjdk/bin

# terraform
autoload -U +X bashcompinit && bashcompinit
complete -o nospace -C /opt/homebrew/bin/terraform terraform

# go
export PATH=$PATH:$HOME/go/bin

# docker desktop
if _file_exists "$HOME/.docker/init-zsh.sh"; then source "$HOME/.docker/init-zsh.sh"; fi

# github copilot cli
if _cmd_exists github-copilot-cli; then eval "$(github-copilot-cli alias -- "$0")"; fi

# curl
export PATH=$PATH:/opt/homebrew/opt/curl/bin

# mise
if _cmd_exists mise; then 
    eval "$(~/.local/bin/mise activate zsh)"
    export PATH=$PATH:$HOME/.local/share/mise/shims
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
export PATH=$PATH:/opt/homebrew/opt/crowdin@4/bin

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
    alias mx="mise x --"
    alias mr="mise run --"
fi
if _cmd_exists terramate; then
    alias t="terramate"
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
