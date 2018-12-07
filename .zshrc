# antigen
source ~/.zshrc.antigen

export EDITOR=vim

# direnv
if which direnv > /dev/null; then eval "$(direnv hook zsh)"; fi

# pyenv
if which pyenv > /dev/null; then eval "$(pyenv init -)"; fi

# golang
if which go > /dev/null; then export PATH=$PATH:$(go env GOPATH)/bin; fi

# Google Cloud SDK
if [ -f "$HOME/google-cloud-sdk/path.zsh.inc" ]; then source "$HOME/google-cloud-sdk/path.zsh.inc"; fi
if [ -f "$HOME/google-cloud-sdk/completion.zsh.inc" ]; then source "$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# android studio (adb)
export PATH=$PATH:$HOME/Library/Android/sdk/platform-tools