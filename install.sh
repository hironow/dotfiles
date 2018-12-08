#!/usr/bin/env bash
set -eu

DOTPATH=$HOME/dotfiles

if [ ! -d "$DOTPATH" ]; then
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
if ! which brew > /dev/null; then 
    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
fi
brew bundle

# install google cloud sdk
if ! which gcloud > /dev/null; then
    curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=$HOME
    gcloud components install \
		app-engine-go \
		beta \
		cloud-datastore-emulator \
		pubsub-emulator
fi

make clean
make deploy