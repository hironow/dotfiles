#!/usr/bin/env bash
# Entry point for `curl ... install.sh | bash` style bootstraps and
# `coder dotfiles -y`. Routes each install step through a per-OS
# dispatch (DOTFILES_OS) so the same script handles macOS hosts,
# Linux Coder workspaces, and (future) Windows scoop hosts.
#
# Per ADR 0005 (Accepted 2026-05-02): a single entry point with
# `step_*` helper functions that branch on DOTFILES_OS. Existing
# `INSTALL_SKIP_*` env vars are preserved as operator overrides
# (OR-combined with the OS auto-skip).
set -eu

# ---- OS identification ---------------------------------------------
case "$(uname -s)" in
  Darwin)
    DOTFILES_OS=mac
    ;;
  Linux)
    DOTFILES_OS=linux
    ;;
  MINGW*|MSYS*|CYGWIN*)
    DOTFILES_OS=windows
    ;;
  *)
    echo "[install] unsupported OS: $(uname -s). Supported: Darwin, Linux, MSYS/MINGW/Cygwin." >&2
    exit 1
    ;;
esac
export DOTFILES_OS

echo "[install] DOTFILES_OS=${DOTFILES_OS}"

# ---- Helpers --------------------------------------------------------

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

_todo_windows() {
  # Marker for steps that don't have a Windows implementation yet.
  # Per ADR 0005 decision the structure is OS-aware now; concrete
  # Windows logic lands in a future ADR + PR when an actual
  # Windows host enters the picture.
  echo "[install] $1: windows TODO (scoop bootstrap to be implemented)"
}

# ---- Repository bootstrap ------------------------------------------

DOTPATH=${DOTPATH:-$HOME/dotfiles}
DOTFILES_REPO=${DOTFILES_REPO:-https://github.com/hironow/dotfiles.git}

if [ ! -d "$DOTPATH" ]; then
  git clone https://github.com/tarjoilija/zgen.git "${HOME}/.zgen"
  git clone "$DOTFILES_REPO" "$DOTPATH"
else
  echo "$DOTPATH already downloaded. Updating..."
  if [ -d "${HOME}/.zgen" ]; then
    (cd "${HOME}/.zgen" && git pull)
  fi
  cd "$DOTPATH"
  git stash
  git checkout main
  git pull origin main
fi

cd "$DOTPATH"

# ---- step_* functions ----------------------------------------------

step_homebrew() {
  if [ -n "${INSTALL_SKIP_HOMEBREW:-}" ]; then
    echo "[install] step_homebrew: skip (INSTALL_SKIP_HOMEBREW=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      # Homebrew is a prerequisite on Mac, not something install.sh
      # bootstraps. The canonical Homebrew install path
      # (curl|bash from raw.githubusercontent.com/Homebrew/install)
      # is a TOFU pipe-to-shell; we keep it out of this script and
      # require the operator to install brew once, manually, with
      # eyes-on, on first machine setup. install.sh thereafter
      # assumes brew is present and fails fast otherwise.
      if ! command -v brew >/dev/null 2>&1; then
        echo "[install] step_homebrew: brew not found on PATH." >&2
        echo "[install] Install Homebrew manually first: https://brew.sh" >&2
        echo "[install] Then re-run install.sh." >&2
        exit 1
      fi
      _eval_brew || true
      ;;
    linux)
      echo "[install] step_homebrew: skip (Linux uses apt + dev container feature)"
      ;;
    windows)
      _todo_windows "step_homebrew"
      ;;
  esac
}

step_gcloud_components() {
  if [ -n "${INSTALL_SKIP_GCLOUD:-}" ]; then
    echo "[install] step_gcloud_components: skip (INSTALL_SKIP_GCLOUD=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      # Use the brew cask instead of `curl sdk.cloud.google.com | bash`
      # (which was a curl-pipe-bash flagged by semgrep). The cask is
      # signed + the formula is hash-pinned in the Homebrew core
      # tap; this matches the trust posture of the rest of the
      # Mac flow.
      if ! command -v gcloud >/dev/null 2>&1; then
        if command -v brew >/dev/null 2>&1; then
          brew install --cask google-cloud-sdk
        else
          echo "[install] step_gcloud_components: brew not on PATH; cannot install gcloud safely. Run step_homebrew first or remove INSTALL_SKIP_HOMEBREW." >&2
          exit 1
        fi
      fi
      ;;
    linux)
      echo "[install] step_gcloud_components: skip (gcloud installed at build time via dev container feature)"
      ;;
    windows)
      _todo_windows "step_gcloud_components"
      ;;
  esac
}

step_just_bootstrap() {
  # Ensure `just` is on PATH before we hand control over to it.
  # Linux's dev container feature already installs just at build
  # time, so this is mostly a Mac path. Mac uses brew exclusively
  # (no curl-pipe-bash fallback) — if brew failed there's a deeper
  # problem and we should fail loud instead of papering over it.
  if command -v just >/dev/null 2>&1; then
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      if command -v brew >/dev/null 2>&1; then
        brew list just >/dev/null 2>&1 || brew install just
      else
        echo "[install] step_just_bootstrap: brew not on PATH and just is missing. Run step_homebrew first or install just manually." >&2
        exit 1
      fi
      ;;
    linux)
      echo "[install] step_just_bootstrap: just expected to be present from dev container feature; not bootstrapping"
      ;;
    windows)
      _todo_windows "step_just_bootstrap"
      ;;
  esac
}

step_brew_bundle() {
  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
    echo "[install] step_brew_bundle: skip (INSTALL_SKIP_ADD_UPDATE=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      just add-brew
      ;;
    linux)
      echo "[install] step_brew_bundle: skip (Linux equivalents covered by apt + dev container feature)"
      ;;
    windows)
      _todo_windows "step_brew_bundle"
      ;;
  esac
}

step_gcloud_bundle() {
  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
    echo "[install] step_gcloud_bundle: skip (INSTALL_SKIP_ADD_UPDATE=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      just add-gcloud
      ;;
    linux)
      echo "[install] step_gcloud_bundle: skip (gcloud components in dev container feature)"
      ;;
    windows)
      _todo_windows "step_gcloud_bundle"
      ;;
  esac
}

step_pnpm_globals() {
  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
    echo "[install] step_pnpm_globals: skip (INSTALL_SKIP_ADD_UPDATE=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac|linux)
      # Linux runs this too: pnpm is provided by the dev container
      # feature and the operator wants the same npm-globals set
      # (vp, markdownlint-cli2, etc.) available on workspaces.
      if command -v pnpm >/dev/null 2>&1; then
        just add-pnpm-g
      else
        echo "[install] step_pnpm_globals: pnpm not on PATH; skipping (dev container feature should install it)"
      fi
      ;;
    windows)
      _todo_windows "step_pnpm_globals"
      ;;
  esac
}

step_update_all() {
  if [ -n "${INSTALL_SKIP_ADD_UPDATE:-}" ]; then
    echo "[install] step_update_all: skip (INSTALL_SKIP_ADD_UPDATE=1)"
    return
  fi
  case "$DOTFILES_OS" in
    mac)
      just update-all
      ;;
    linux)
      echo "[install] step_update_all: skip (apt + mise manage updates)"
      ;;
    windows)
      _todo_windows "step_update_all"
      ;;
  esac
}

step_symlink_dotfiles() {
  # Cross-platform: symlinks the operator's ~/.zshrc etc. to the
  # tracked dotfiles. Required on every OS.
  just clean
  just deploy
}

step_sheldon() {
  # Cross-platform: zsh plugin lock. Sheldon is provided by brew on
  # Mac and by the dev container feature on Linux. Windows path is
  # TODO until a Windows host actually exists.
  case "$DOTFILES_OS" in
    mac|linux)
      if command -v sheldon >/dev/null 2>&1; then
        sheldon lock --update >/dev/null || true
      else
        echo "[install] step_sheldon: sheldon not on PATH; skipping"
      fi
      ;;
    windows)
      _todo_windows "step_sheldon"
      ;;
  esac
}

# ---- Drive ----------------------------------------------------------

step_homebrew
step_gcloud_components
step_just_bootstrap
step_brew_bundle
step_gcloud_bundle
step_pnpm_globals
step_update_all
step_symlink_dotfiles
step_sheldon

echo "[install] done (DOTFILES_OS=${DOTFILES_OS})"
