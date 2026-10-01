#!/usr/bin/env bash
# Body of `just deploy` (see justfile). Kept OUT of the justfile as a plain
# script so the recipe stays linewise: shebang recipes bypass
# `set windows-shell` and resolve `env bash` to WSL's System32 bash from
# PowerShell (tests/unit/test_deploy_clean_linewise.py guards this).
# Windows native (MSYS/MINGW/CYGWIN) gets a cross-platform subset only
# (starship.toml + gitignore-global). zsh/sheldon/tmux/ghostty/fzf-tab
# are Unix-only and are skipped. See ADR 0018.
set -eu
# shellcheck source=scripts/ps_profile_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/ps_profile_lib.sh"

ensure_zprofile_login_path() {
  # A zsh login shell reads ~/.zprofile, never ~/.profile, and only an
  # interactive one reads .zshrc: `zsh -lc '...'` (scripts, agents) missed the
  # ~/.local/bin bash got from ~/.profile. Append a block, not a symlink: a Mac
  # usually keeps its own lines (brew shellenv) in ~/.zprofile.
  marker="# >>> dotfiles managed block: login PATH >>>"
  if grep -qF "$marker" "$HOME/.zprofile" 2>/dev/null; then
    return 0
  fi
  {
    printf '\n%s\n' "$marker"
    # shellcheck disable=SC2016 # written literally; expands at login
    printf '%s\n' 'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) [ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH" ;; esac'
    printf '%s\n' "# <<< end dotfiles managed block <<<"
  } >>"$HOME/.zprofile"
}

# Agent steps every OS runs once mise has installed the tools: the script under
# scripts/, the recipe that re-runs it by hand, and what it does. One list for
# both paths: the native Windows branch exits early, and a step written only in
# the shared tail never reached it (headroom's MCP server, once).
AGENT_STEPS='install_pi_extensions.py pi-extensions-install Installing Pi extensions
claude_plugins.py claude-plugins-install Installing Claude Code plugins
headroom_mcp.py headroom-mcp-register Registering headroom'"'"'s MCP server'

run_agent_steps() {
  while read -r script recipe what; do
    echo "==> $what..."
    mise -C / exec -- python ~/dotfiles/scripts/"$script" ||
      echo "==> WARN: $script failed; run 'just $recipe' after resolving the error"
  done <<EOF
$AGENT_STEPS
EOF
}

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    echo "==> Deploy dotfiles (windows subset)..."
    mkdir -p ~/.config
    cp -f ~/dotfiles/starship.toml ~/.config/starship.toml
    mkdir -p ~/.config/git
    cp -f ~/dotfiles/dump/gitignore-global ~/.config/git/ignore
    mkdir -p ~/.config/mise
    cp -f ~/dotfiles/config/mise/config.toml ~/.config/mise/config.toml
    # PowerShell 7 $PROFILE managed blocks. The Microsoft.PowerShell_profile.ps1
    # pwsh actually loads — not always under $HOME/Documents (OneDrive
    # redirects it; scripts/ps_profile_lib.sh).
    ps_profile="$(resolve_ps_profile)"
    ps_marker_end="# <<< end dotfiles managed block <<<"
    mkdir -p "$(dirname "$ps_profile")"
    touch "$ps_profile"
    # mise activate block (ADR 0024). Written before the starship block:
    # starship is mise-managed, so its Get-Command needs mise on PATH first.
    ps_mise_marker_begin="# >>> dotfiles managed block: mise activate >>>"
    if grep -qF "$ps_mise_marker_begin" "$ps_profile"; then
      echo "==> PowerShell \$PROFILE mise-activate block already present (skip)"
    else
      {
        printf '\n%s\n' "$ps_mise_marker_begin"
        # shellcheck disable=SC2016  # literal backticks: written verbatim into $PROFILE
        printf '# Managed by `just deploy` (see ADR 0024). Edits inside this block are overwritten on next deploy.\n'
        printf 'if (Get-Command mise -ErrorAction SilentlyContinue) {\n'
        printf '    Invoke-Expression (&mise activate pwsh | Out-String)\n'
        printf '}\n'
        printf '%s\n' "$ps_marker_end"
      } >> "$ps_profile"
      echo "==> PowerShell \$PROFILE updated with mise-activate block"
    fi
    # starship init block (ADR 0022), after mise activate. Profiles deployed
    # with the old order carry it first, where it silently skips unless mise's
    # shims are on the persisted PATH (runner hosts only); blocks already
    # present are never rewritten, so drop it here to re-append it below.
    if ps_profile_starship_before_mise "$ps_profile"; then
      ps_profile_drop_block "$ps_profile" 'starship init'
      echo "==> PowerShell \$PROFILE starship-init block moved after mise activate"
    fi
    ps_marker_begin="# >>> dotfiles managed block: starship init >>>"
    if grep -qF "$ps_marker_begin" "$ps_profile"; then
      echo "==> PowerShell \$PROFILE starship-init block already present (skip)"
    else
      {
        printf '\n%s\n' "$ps_marker_begin"
        # shellcheck disable=SC2016  # literal backticks: written verbatim into $PROFILE
        printf '# Managed by `just deploy` (see ADR 0022). Edits inside this block are overwritten on next deploy.\n'
        printf 'if (Get-Command starship -ErrorAction SilentlyContinue) {\n'
        printf '    Invoke-Expression (&starship init powershell)\n'
        printf '}\n'
        printf '%s\n' "$ps_marker_end"
      } >> "$ps_profile"
      echo "==> PowerShell \$PROFILE updated with starship-init block"
    fi
    # PowerShell 7 $PROFILE — mise node corepack carve-out (Windows; ADR
    # 0031). mise's global `[settings.node] corepack = true` runs corepack
    # during `mise install node`, throwing `EPERM ...\Program Files\nodejs\
    # pnpx.CMD` on Windows; since `mise exec` installs missing tools first,
    # that blocks every mise-wrapped recipe. Node is bun-only on Windows
    # (ADR 0027), so export MISE_NODE_COREPACK=0. Its own managed block
    # (fresh marker) appends even on hosts that already carry the starship
    # (0022) / mise-activate (0024) blocks.
    ps_corepack_marker_begin="# >>> dotfiles managed block: mise node corepack >>>"
    if grep -qF "$ps_corepack_marker_begin" "$ps_profile"; then
      echo "==> PowerShell \$PROFILE mise-corepack block already present (skip)"
    else
      {
        printf '\n%s\n' "$ps_corepack_marker_begin"
        # shellcheck disable=SC2016  # literal backticks + PowerShell $env: syntax, both written verbatim
        printf '# Managed by `just deploy`. Edits inside this block are overwritten on next deploy.\n'
        # shellcheck disable=SC2016  # $env: is PowerShell syntax for the target $PROFILE, not a shell expansion
        printf '$env:MISE_NODE_COREPACK = "0"\n'
        printf '%s\n' "$ps_marker_end"
      } >> "$ps_profile"
      echo "==> PowerShell \$PROFILE updated with mise-corepack block"
    fi
    # Install the global mise toolset (ADR 0033). deploy copies the config
    # above; native Windows mise reads ~/.config/mise/config.toml (verified
    # via `mise config ls`). `-C /` scopes to the global config only.
    # MISE_NODE_COREPACK=0 avoids the Program-Files-node corepack EPERM
    # (ADR 0031). Best-effort, but say so loudly on failure (a fresh host may
    # need network or `mise trust`).
    if command -v mise >/dev/null 2>&1; then
      echo "==> Installing global mise tools (best-effort)..."
      MISE_NODE_COREPACK=0 mise -C / install || echo "==> WARN: global mise tool install incomplete; re-run 'MISE_NODE_COREPACK=0 mise -C / install' (needs network; may need 'mise trust')"
    else
      echo "==> mise not on PATH; skipping global tool install (install mise via scoop, then re-run 'just deploy')"
    fi
    # Opt-in Jev commands (j-cc, j-pi) for the next PowerShell session. Keep the
    # key out of this profile; the operator supplies TYPESAFE_API_KEY as an env
    # var (or ~/.config/jev/env). The block is rewritten on every deploy, so a rename
    # reaches profiles that already carry it.
    ps_jev_marker_begin="# >>> dotfiles managed block: Jev launchers >>>"
    if grep -qF "$ps_jev_marker_begin" "$ps_profile"; then
      ps_profile_drop_block "$ps_profile" 'Jev launchers'
    fi
    {
      printf '\n%s\n' "$ps_jev_marker_begin"
      cat <<'POWERSHELL'
function j-cc { & mise exec -- python "$HOME/dotfiles/scripts/jev_launch.py" claude @args }
function j-pi { & mise exec -- python "$HOME/dotfiles/scripts/jev_launch.py" pi @args }
POWERSHELL
      printf '%s\n' "$ps_marker_end"
    } >> "$ps_profile"
    echo "==> PowerShell \$PROFILE updated with Jev launchers"
    if command -v mise >/dev/null 2>&1; then
      (export MISE_NODE_COREPACK=0 && run_agent_steps)
    fi
    # git aliases [include] managed block (ADR 0033). Wires ONLY
    # aliases.gitconfig (pure [alias] entries) — deliberately NOT
    # shared.gitconfig: re-including shared after a manual PC-local override
    # (e.g. gpgsign=false on a keyless host) would clobber it. Identity /
    # signing / shared stay manual per ADR 0021. Reuses $ps_marker_end;
    # git treats '#' lines as comments so the markers are inert.
    gitconfig="$HOME/.gitconfig"
    git_marker_begin="# >>> dotfiles managed block: git aliases include >>>"
    touch "$gitconfig"
    if grep -qF "$git_marker_begin" "$gitconfig"; then
      echo "==> ~/.gitconfig git-aliases block already present (skip)"
    else
      {
        printf '\n%s\n' "$git_marker_begin"
        # shellcheck disable=SC2016  # literal backticks: written verbatim into ~/.gitconfig
        printf '# Managed by `just deploy` (ADR 0033). Only aliases — identity/signing/shared stay manual (ADR 0021).\n'
        printf '[include]\n'
        printf '\tpath = ~/dotfiles/config/git/aliases.gitconfig\n'
        printf '%s\n' "$ps_marker_end"
      } >> "$gitconfig"
      echo "==> ~/.gitconfig updated with git-aliases include block"
    fi
    echo "==> Deploy complete (windows subset per ADR 0018/0022/0024/0031/0033; corepack carve-out per ADR 0017/0027; Unix-only artifacts skipped)"
    exit 0
    ;;
esac
echo "==> Start to deploy dotfiles to home directory."
ln -sf ~/dotfiles/.zshrc ~/.zshrc
ensure_zprofile_login_path
mkdir -p ~/.config/sheldon
ln -sf ~/dotfiles/sheldon-plugins.toml ~/.config/sheldon/plugins.toml
ln -sf ~/dotfiles/starship.toml ~/.config/starship.toml
ln -sf ~/dotfiles/tools/tmux/tmux.conf ~/.tmux.conf
mkdir -p ~/.config/ghostty
ln -sf ~/dotfiles/tools/ghostty-config ~/.config/ghostty/config
mkdir -p ~/.config/git
cp ~/dotfiles/dump/gitignore-global ~/.config/git/ignore
mkdir -p ~/.config/mise
ln -sf ~/dotfiles/config/mise/config.toml ~/.config/mise/config.toml
if command -v mise >/dev/null 2>&1; then
    echo "==> Provisioning global mise tools (best-effort)..."
    # cwd=/ so only the global ~/.config/mise/config.toml resolves; a
    # HOME-level ~/mise.toml / ~/.tool-versions must NOT widen the set.
    # Best-effort: never abort the symlink deploy on a transient network
    # or registry failure (resolving "latest" needs an online lookup).
    mise -C / install || echo "==> WARN: global mise tool install incomplete; re-run 'mise -C / install' (needs network for 'latest')"
else
    echo "==> mise not on PATH; skipping global tool install (install mise, then run 'mise -C / install')"
fi
echo "==> Installing plugins..."
if command -v sheldon >/dev/null 2>&1; then
    sheldon lock
elif command -v mise >/dev/null 2>&1 && mise x -- sh -c 'command -v sheldon' >/dev/null 2>&1; then
    mise x -- sheldon lock
else
    echo "==> sheldon not found; skipping lock (provided by brew / devcontainer feature / mise)"
fi
if [ ! -d ~/.local/share/fzf-tab ]; then
    echo "==> Installing fzf-tab..."
    git clone --depth 1 https://github.com/Aloxaf/fzf-tab ~/.local/share/fzf-tab
fi
if command -v mise >/dev/null 2>&1; then
    run_agent_steps
elif command -v pi >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    python3 ~/dotfiles/scripts/install_pi_extensions.py || echo "==> WARN: Pi extension installation failed; run 'just pi-extensions-install' after resolving the error"
    echo "==> mise not on PATH; run 'just claude-plugins-install' and 'just headroom-mcp-register' after provisioning"
else
    echo "==> mise not on PATH; run 'just pi-extensions-install', 'just claude-plugins-install' and 'just headroom-mcp-register' after provisioning"
fi
echo "==> Deploy complete!"
