#!/usr/bin/env bash
set -eu

# shellcheck disable=SC2317
_eval_brew() {
  # Initialize Homebrew environment across common installations.
  if command -v brew >/dev/null 2>&1; then
    eval "$(brew shellenv)"
    return
  fi
  if [ -x "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    return
  fi
  if [ -x "$HOME/.linuxbrew/bin/brew" ]; then
    eval "$("$HOME/.linuxbrew/bin/brew" shellenv)"
    return
  fi
  if [ -x "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
    return
  fi
}

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
if [ -z "${INSTALL_SKIP_HOMEBREW:-}" ]; then
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  # Ensure brew is initialized even if pre-installed in a non-default path
  _eval_brew || true
else
  echo "[install] Skip Homebrew installation (INSTALL_SKIP_HOMEBREW=1)"
fi
# install google cloud sdk
if [ -z "${INSTALL_SKIP_GCLOUD:-}" ]; then
  if ! command -v gcloud >/dev/null; then
    curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
  fi
else
  echo "[install] Skip Google Cloud SDK installation (INSTALL_SKIP_GCLOUD=1)"
fi

# ensure just is available
if ! command -v just >/dev/null 2>&1; then
  # Try via brew when available
  if command -v brew >/dev/null 2>&1; then
    brew list just >/dev/null 2>&1 || brew install just || true
  fi
fi

# execute commands via just
if [ -z "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
  just add-all
  just update-all
else
  echo "[install] Skip add/update steps (INSTALL_SKIP_ADD_UPDATE=1)"
fi

just clean
just deploy
