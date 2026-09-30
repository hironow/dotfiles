#!/usr/bin/env bash
# Body of `just clean` (see justfile). Kept OUT of the justfile as a plain
# script so the recipe stays linewise: shebang recipes bypass
# `set windows-shell` and resolve `env bash` to WSL's System32 bash from
# PowerShell (tests/unit/test_deploy_clean_linewise.py guards this).
# Windows native removes only what `just deploy` placed (ADR 0018 subset).
set -eu
# shellcheck source=scripts/ps_profile_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/ps_profile_lib.sh"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    echo "==> Remove dotfiles (windows subset)..."
    rm -vrf ~/.config/starship.toml
    rm -vrf ~/.config/git/ignore
    rm -vrf ~/.config/mise/config.toml
    # PowerShell 7 Microsoft.PowerShell_profile.ps1: the one pwsh loads, plus
    # the legacy $HOME/Documents path that deploy used before it resolved the
    # real $PROFILE (hosts with OneDrive-redirected Documents still carry the
    # managed blocks there). Sweeping the same file twice is a no-op.
    for ps_profile in "$(resolve_ps_profile)" "$(ps_profile_legacy)"; do
      # Remove PowerShell starship-init block (idempotent; ADR 0022).
      if [ -f "$ps_profile" ] && grep -qF "# >>> dotfiles managed block: starship init >>>" "$ps_profile"; then
        sed -i '/# >>> dotfiles managed block: starship init >>>/,/# <<< end dotfiles managed block <<</d' "$ps_profile"
        echo "==> PowerShell \$PROFILE starship-init block removed"
      fi
      # Remove PowerShell mise-activate block (idempotent; ADR 0024).
      if [ -f "$ps_profile" ] && grep -qF "# >>> dotfiles managed block: mise activate >>>" "$ps_profile"; then
        sed -i '/# >>> dotfiles managed block: mise activate >>>/,/# <<< end dotfiles managed block <<</d' "$ps_profile"
        echo "==> PowerShell \$PROFILE mise-activate block removed"
      fi
      # Remove PowerShell mise-node-corepack block (idempotent; ADR 0031).
      if [ -f "$ps_profile" ] && grep -qF "# >>> dotfiles managed block: mise node corepack >>>" "$ps_profile"; then
        sed -i '/# >>> dotfiles managed block: mise node corepack >>>/,/# <<< end dotfiles managed block <<</d' "$ps_profile"
        echo "==> PowerShell \$PROFILE mise-corepack block removed"
      fi
    done
    # Remove git-aliases include block from ~/.gitconfig (idempotent; ADR 0033).
    gitconfig="$HOME/.gitconfig"
    if [ -f "$gitconfig" ] && grep -qF "# >>> dotfiles managed block: git aliases include >>>" "$gitconfig"; then
      sed -i '/# >>> dotfiles managed block: git aliases include >>>/,/# <<< end dotfiles managed block <<</d' "$gitconfig"
      echo "==> ~/.gitconfig git-aliases block removed"
    fi
    exit 0
    ;;
esac
echo "==> Remove dotfiles in your home directory..."
rm -vrf ~/.zshrc
rm -vrf ~/.config/sheldon/plugins.toml
rm -vrf ~/.config/starship.toml
rm -vrf ~/.tmux.conf
rm -vrf ~/.config/ghostty/config
rm -vrf ~/.config/mise/config.toml
