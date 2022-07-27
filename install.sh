#!/usr/bin/env bash
set -eu

DOTPATH=$HOME/dotfiles

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
  echo "eval "$(/opt/homebrew/bin/brew shellenv)"" >> "$HOME"/.zprofile
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

make add-brew

# install google cloud sdk
if ! command -v gcloud >/dev/null; then
  curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
fi
make add-gcloud

# install pnpm global packages
pnpm setup
make add-pnpm-global

make update-all

make clean
make deploy
