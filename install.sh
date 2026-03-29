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

_source_nix() {
  if [ -e '/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh' ]; then
    # shellcheck disable=SC1091
    . '/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh'
  elif [ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ]; then
    # Single-user / --init none installs
    # shellcheck disable=SC1091
    . "$HOME/.nix-profile/etc/profile.d/nix.sh"
  fi
}

DOTPATH=${DOTPATH:-$HOME/dotfiles}
DOTFILES_REPO=${DOTFILES_REPO:-https://github.com/hironow/dotfiles.git}

if [ ! -d "$DOTPATH" ]; then
  git clone "$DOTFILES_REPO" "$DOTPATH"
else
  echo "$DOTPATH already downloaded. Updating..."
  cd "$DOTPATH"
  git stash
  git checkout main
  git pull origin main
fi

cd "$DOTPATH"

# --- Nix (primary package manager) ---
if [ -z "${INSTALL_SKIP_NIX:-}" ]; then
  if ! command -v nix >/dev/null 2>&1; then
    echo "[install] Installing Nix (Determinate Installer)..."
    # Docker/containers lack systemd; use linux --init none
    if [ ! -d /run/systemd/system ]; then
      NIX_INSTALL_ARGS="install linux --init none --no-confirm"
    else
      NIX_INSTALL_ARGS="install --no-confirm"
    fi
    # shellcheck disable=SC2086
    curl --proto '=https' --tlsv1.2 -sSf -L \
      https://install.determinate.systems/nix | sh -s -- $NIX_INSTALL_ARGS
    _source_nix
  else
    echo "[install] Nix already installed."
    _source_nix
  fi
else
  echo "[install] Skip Nix installation (INSTALL_SKIP_NIX=1)"
  _source_nix
fi

# --- Home Manager (dotfiles + packages) ---
if [ -z "${INSTALL_SKIP_HM:-}" ]; then
  if command -v nix >/dev/null 2>&1; then
    echo "[install] Applying Home Manager configuration..."
    system=$(nix eval --raw --impure --expr 'builtins.currentSystem')
    username=$(whoami)
    nix run home-manager -- switch --flake ".#${username}@${system}" --impure
  else
    echo "[install] WARNING: nix not found, skipping Home Manager."
  fi
else
  echo "[install] Skip Home Manager (INSTALL_SKIP_HM=1)"
fi

# --- Homebrew (cask/mas/vscode only) ---
if [ -z "${INSTALL_SKIP_HOMEBREW:-}" ]; then
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  _eval_brew || true
else
  echo "[install] Skip Homebrew installation (INSTALL_SKIP_HOMEBREW=1)"
fi

# --- Google Cloud SDK ---
if [ -z "${INSTALL_SKIP_GCLOUD:-}" ]; then
  if ! command -v gcloud >/dev/null; then
    curl https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
  fi
else
  echo "[install] Skip Google Cloud SDK installation (INSTALL_SKIP_GCLOUD=1)"
fi

# --- ensure just is available (fallback if Nix didn't provide it) ---
if ! command -v just >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew list just >/dev/null 2>&1 || brew install just || true
  fi
  if ! command -v just >/dev/null 2>&1; then
    echo "[install] Installing just via curl..."
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to "$HOME/.local/bin"
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

# --- Post-Nix package installation ---
if [ -z "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
  just add-brew
  just add-gcloud
  just add-pnpm-g
else
  echo "[install] Skip add/update steps (INSTALL_SKIP_ADD_UPDATE=1)"
fi
