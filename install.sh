#!/usr/bin/env bash
set -eu

DOTPATH=${DOTPATH:-$HOME/dotfiles}

if [ ! -d "$DOTPATH" ]; then
  git clone https://github.com/tarjoilija/zgen.git "${HOME}/.zgen"
  git clone https://github.com/hironow/dotfiles.git "$DOTPATH"
else
  echo "$DOTPATH already downloaded. Updating..."
  cd "$DOTPATH"
  git stash
  git checkout main
  git pull origin main
fi

cd "$DOTPATH"

# install homebrew
if ! command -v brew >/dev/null; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
# install google cloud sdk
if ! command -v gcloud >/dev/null; then
  curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
fi

# ensure just is available
if ! command -v just >/dev/null; then
  brew list just >/dev/null 2>&1 || brew install just
fi

# execute commands via just
just add-all
just update-all

just clean
just deploy
