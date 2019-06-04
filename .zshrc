# antigen
source ~/.zshrc.antigen

export EDITOR=vim

# homebrew
export PATH="/usr/local/sbin:$PATH"

# direnv
if which direnv > /dev/null; then eval "$(direnv hook zsh)"; fi

# goenv
export GOENV_ROOT="$HOME/.goenv";
export PATH="$HOME/.goenv/bin:$PATH";
if which goenv > /dev/null; then eval "$(goenv init -)"; fi

# golang
if which go > /dev/null; then
    export PATH=$PATH:$(go env GOPATH)/bin;
    export PATH=$PATH:$(go env GOROOT)/bin;
fi

# Google Cloud SDK
if [ -f "$HOME/google-cloud-sdk/path.zsh.inc" ]; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if [ -f "$HOME/google-cloud-sdk/completion.zsh.inc" ]; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools

# Wasmer
export WASMER_DIR="/Users/hironow/.wasmer"
[ -s "$WASMER_DIR/wasmer.sh" ] && source "$WASMER_DIR/wasmer.sh"  # This loads wasmer
