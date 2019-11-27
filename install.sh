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
  git checkout master
  git pull origin master
fi

cd "$DOTPATH"

# install homebrew
if ! command -v brew >/dev/null; then
  /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
fi
brew bundle

# install google cloud sdk
if ! command -v gcloud >/dev/null; then
  curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
fi

# install gcloud components
make add-gcloud

# install yarn global packages
make add-yarn-global

make clean
make deploy
