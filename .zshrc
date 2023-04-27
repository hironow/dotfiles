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

export SPACESHIP_EXIT_CODE_SHOW=true

export EDITOR=vim

# local
export PATH=$PATH:/usr/local/bin

# direnv
if which direnv > /dev/null; then eval "$(direnv hook zsh)"; fi

# anyenv
if which anyenv > /dev/null; then eval "$(anyenv init -)"; fi

# Google Cloud SDK
if [ -f "$HOME/google-cloud-sdk/path.zsh.inc" ]; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if [ -f "$HOME/google-cloud-sdk/completion.zsh.inc" ]; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools

# Wasmer
export WASMER_DIR="$HOME/.wasmer"
[ -s "$WASMER_DIR/wasmer.sh" ] && source "$WASMER_DIR/wasmer.sh"  # This loads wasmer

# tabtab source for serverless package
# uninstall by removing these lines or running `tabtab uninstall serverless`
[[ -f $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/serverless.zsh ]] && . $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/serverless.zsh
# tabtab source for sls package
# uninstall by removing these lines or running `tabtab uninstall sls`
[[ -f $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/sls.zsh ]] && . $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/sls.zsh
# tabtab source for slss package
# uninstall by removing these lines or running `tabtab uninstall slss`
[[ -f $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/slss.zsh ]] && . $HOME/.config/yarn/global/node_modules/serverless/node_modules/tabtab/.completions/slss.zsh

# k8s
if which kubectl > /dev/null; then source <(kubectl completion zsh); fi

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
if [ -f "$HOME/.docker/init-zsh.sh" ]; then source $HOME/.docker/init-zsh.sh; fi

# github copilot cli
if which github-copilot-cli > /dev/null; then eval "$(github-copilot-cli alias -- "$0")"; fi

# pyenv & poetry
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
export PATH="$HOME/.poetry/bin:$PATH"
if which poetry > /dev/null; then poetry completions zsh > ~/.zfunc/_poetry; fi