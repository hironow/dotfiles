# https://just.systems

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# External commands
MARKDOWNLINT := "mise exec -- markdownlint-cli2"
PDOC := "uv run pdoc"

# Default: show help
[group('Meta')]
default: help

# Help: list available recipes
[group('Meta')]
help:
    @just --list --unsorted

# Lint markdown files
[group('Check')]
lint-md:
    @{{MARKDOWNLINT}} --fix "docs/**/*.md" "README.md" "experiments/**/*.md" "!submodules/**" "!sets/**" "!input/**" "!output/**"

[group('Check')]
pdoc port="8888" pkg=".":
    {{PDOC}} --port {{port}} {{pkg}}


# ------------------------------
# Project Management
# ------------------------------

# Run meta semgrep rules against rule files (ROOT_AGENTS.md etc.)
[group('Validation')]
meta-semgrep:
    uvx semgrep --config .semgrep/rules/meta/ --error .

# Verify meta rules themselves with their test annotations
[group('Validation')]
meta-semgrep-test:
    uvx semgrep --test --config .semgrep/rules/meta/

# Full validation of rule files
[group('Validation')]
validate: meta-semgrep-test meta-semgrep

# Install: setup tools via mise
[group('Setup')]
install:
    # Install tools via mise (versions are managed in mise.toml)
    mise install

# Deploy: symlink dotfiles to home and install plugins
[group('Setup')]
deploy:
    @echo "==> Start to deploy dotfiles to home directory."
    ln -sf ~/dotfiles/.zshrc ~/.zshrc
    mkdir -p ~/.config/sheldon
    ln -sf ~/dotfiles/sheldon-plugins.toml ~/.config/sheldon/plugins.toml
    ln -sf ~/dotfiles/starship.toml ~/.config/starship.toml
    ln -sf ~/dotfiles/tools/tmux/tmux.conf ~/.tmux.conf
    mkdir -p ~/.config/ghostty
    ln -sf ~/dotfiles/tools/ghostty-config ~/.config/ghostty/config
    mkdir -p ~/.config/git
    cp ~/dotfiles/dump/gitignore-global ~/.config/git/ignore
    @echo "==> Installing plugins..."
    sheldon lock
    @if [ ! -d ~/.local/share/fzf-tab ]; then \
        echo "==> Installing fzf-tab..."; \
        git clone --depth 1 https://github.com/Aloxaf/fzf-tab ~/.local/share/fzf-tab; \
    fi
    @echo "==> Deploy complete!"

# Sync: copy ROOT_AGENTS files to agent instruction directories
# Default scope = .claude only. Pass targets to widen:
#   just sync-agents               -> ~/.claude only
#   just sync-agents a b           -> + ~/.claude-work-a, ~/.claude-work-b
#   just sync-agents all           -> every defined agent
# Aliases: p=claude, a/b/c/d=work-a..d, g=gemini, x=codex, agents=agents-global
[group('Agents')]
sync-agents *args:
    @uv run scripts/sync_agents.py {{ args }}

# Sync (preview): show what would be synced without making changes
[group('Agents')]
sync-agents-preview *args:
    @uv run scripts/sync_agents.py --preview {{ args }}

# Sync (auto): sync without prompts (default scope = .claude only)
[group('Agents')]
sync-agents-auto *args:
    @uv run scripts/sync_agents.py --yes {{ args }}

# Sync (override): full replace — dotfiles wins, orphans removed, no prompts
[group('Agents')]
sync-agents-override *args:
    @uv run scripts/sync_agents.py --override {{ args }}

# Sync (orphans): show target-only items that would be removed
[group('Agents')]
sync-agents-orphans *args:
    @uv run scripts/sync_agents.py --orphans {{ args }}

# Import only: target -> dotfiles. No forward sync, no orphan removal.
# Default scope = .claude only. Pass targets to widen (same aliases as sync-agents).
# Every selected agent becomes an import source — is_import_source flag is ignored.
#   just import-agents              -> from ~/.claude only
#   just import-agents a b          -> from ~/.claude-work-a + b
#   just import-agents all          -> from every defined agent
[group('Agents')]
import-agents *args:
    @uv run scripts/sync_agents.py --import-only {{ args }}

# Import only (preview): show what would be imported without writing
[group('Agents')]
import-agents-preview *args:
    @uv run scripts/sync_agents.py --import-only --preview {{ args }}

# Clean: remove deployed dotfiles (~/.zshrc, ~/.config/sheldon/plugins.toml, ~/.config/starship.toml)
[group('Setup')]
clean:
    @echo "==> Remove dotfiles in your home directory..."
    rm -vrf ~/.zshrc
    rm -vrf ~/.config/sheldon/plugins.toml
    rm -vrf ~/.config/starship.toml
    rm -vrf ~/.tmux.conf
    rm -vrf ~/.config/ghostty/config

# Clean cache: remove zsh-related caches (compinit, fzf, zoxide, kubectl, sheldon)
[group('Setup')]
clean-cache:
    @echo "==> Remove zsh caches..."
    rm -vrf ~/.cache/zsh/
    rm -vrf ~/.zcompdump*
    rm -vrf ~/.local/share/sheldon/
    rm -vrf ~/.local/share/fzf-tab/

# Clean all: remove both dotfiles and caches
[group('Setup')]
clean-all: clean clean-cache

# Clean work env: reset a claude-work-X directory (remove synced skills/commands/agents, empty CLAUDE.md)
# Usage: just clean-work-env d
[group('Agents')]
clean-work-env target:
    #!/usr/bin/env bash
    set -eu -o pipefail
    case "{{ target }}" in
      a) config_dir="$HOME/.claude-work-a" ;;
      b) config_dir="$HOME/.claude-work-b" ;;
      c) config_dir="$HOME/.claude-work-c" ;;
      d) config_dir="$HOME/.claude-work-d" ;;
      *) echo "ERROR: unknown target '{{ target }}'. Use: a, b, c, d"; exit 1 ;;
    esac
    if [ ! -d "$config_dir" ]; then
      echo "❌ $config_dir does not exist"
      exit 1
    fi
    echo "🧹 Cleaning $config_dir ..."
    echo "--- Emptying CLAUDE.md ---"
    : > "$config_dir/CLAUDE.md"
    echo "--- Removing skills/ ---"
    rm -rf "$config_dir/skills"
    echo "--- Removing commands/ ---"
    rm -rf "$config_dir/commands"
    echo "--- Removing agents/ ---"
    rm -rf "$config_dir/agents"
    echo "--- Removing plans/ ---"
    rm -rf "$config_dir/plans"
    echo "--- Removing session-env/ ---"
    rm -rf "$config_dir/session-env"
    echo "--- Removing shell-snapshots/ ---"
    rm -rf "$config_dir/shell-snapshots"
    echo "✅ $config_dir cleaned (plugins, projects, history preserved)"

# Dump: write Homebrew bundle and global gitignore into dump/
[group('Setup')]
dump:
    # Dump current brew bundle
    rm -f ./dump/Brewfile && (cd ./dump && brew bundle dump)
    # Dump global gitignore
    cp ~/.config/git/ignore ./dump/gitignore-global
    # Dump installed gcloud components (restore with: just add-gcloud)
    gcloud components list --filter='state.name=Installed' --format='value(id)' 2>/dev/null | sort -u > ./dump/gcloud
    # Dump installed pnpm globals (restore with: just add-pnpm-g)
    # Use --json so only top-level deps are captured; --parseable would also include the .pnpm content-addressed store.
    env -C "$HOME" pnpm ls -g --depth 0 --json 2>/dev/null | jq -r '.[0].dependencies | keys[]' | sort -u > ./dump/npm-global


# ------------------------------
# Tests
# ------------------------------

# Test: build dev container (if available) and run pytest (verbose).
# Uses the @devcontainers/cli to produce dotfiles-just-sandbox:latest
# from .devcontainer/devcontainer.json — same image CI builds via the
# devcontainers/ci action.
[group('Test')]
test:
    @echo '🧪 Preparing dev container image (if devcontainer CLI is available)...'
    @if command -v docker >/dev/null 2>&1 && command -v devcontainer >/dev/null 2>&1; then \
    	echo '→ devcontainer CLI detected; building image'; \
    	devcontainer build --workspace-folder . --image-name dotfiles-just-sandbox:latest || echo '⚠️ devcontainer build failed (tests may skip)'; \
    else \
    	echo '⚠️ docker or @devcontainers/cli not found; tests may skip'; \
    	echo '   Hint: npm i -g @devcontainers/cli'; \
    fi
    @echo '🧪 Running pytest (verbose with skip reasons)...'
    uvx pytest -v -ra tests/test_just_sandbox.py tests/test_devcontainer.py
    @echo '✅ Tests finished.'

# Test (install): run install.sh verification in Docker
[group('Test')]
test-install:
    @echo '🧪 Running install.sh verification in Docker...'
    docker build -f tests/docker/InstallTest.Dockerfile .
    @echo '✅ Verification passed.'

# Self-check: quick, safe health checks with summary
[group('Setup')]
self-check with_tests="":
    #!/usr/bin/env bash
    set -u
    echo '🔎 Running self-check...'
    ok=0; warn=0; err=0
    step_ok(){ printf 'OK   %s\n' "$1"; ok=$((ok+1)); }
    step_warn(){ printf 'WARN %s\n' "$1"; warn=$((warn+1)); }
    step_err(){ printf 'ERR  %s\n' "$1"; err=$((err+1)); }

    # just is callable
    if just --version >/dev/null 2>&1; then step_ok 'just available'; else step_err 'just missing'; fi

    # doctor (should return 0; prints its own summary)
    doc_out=$(just doctor 2>&1); rc=$?
    printf '%s\n' "$doc_out"
    if [ "$rc" -eq 0 ]; then step_ok 'doctor'; else step_err 'doctor failed'; fi

    # PATH duplicates (treat rc=2 as WARN)
    set +e
    dup_out=$(just validate-path-duplicates 2>&1)
    dup_rc=$?
    set -e
    case "$dup_rc" in
      0) step_ok 'path duplicates: none' ;;
      2) printf '%s\n' "$dup_out"; step_warn 'path duplicates: found' ;;
      *) printf '%s\n' "$dup_out"; step_warn 'path duplicates: validator error' ;;
    esac

    # Optional: run quick validate tests inside Docker if requested
    if [ -n "{{ with_tests }}" ]; then
      if command -v docker >/dev/null 2>&1; then
        echo '🧪 Running sandbox validate tests...'
        if just test-mark marker=validate; then step_ok 'tests: validate'; else step_err 'tests: validate failed'; fi
      else
        step_warn 'docker missing: skip tests'
      fi
    fi

    echo "Self-check summary: ok=$ok warn=$warn err=$err"
    if [ "$err" -gt 0 ]; then exit 1; fi
    :

# Test (by marker): run tests filtered by -m MARKER
[group('Test')]
test-mark marker="":
    @echo '🧪 Running pytest with marker:' '{{ marker }}'
    @if [ -n "{{ marker }}" ]; then \
    	uvx pytest -v -ra -m '{{ marker }}' tests/test_just_sandbox.py tests/test_devcontainer.py; \
    else \
    	echo 'Marker is empty. Usage: just test-mark marker=install'; \
    	exit 2; \
    fi

# ------------------------------
# Formatting
# ------------------------------

# fmt: writes formatting fixes in place. Tool per language:
#   - Python  : `uvx ruff format .` (excludes live in pyproject.toml)
#   - Markdown: `markdownlint-cli2 --fix`
#   - JS/TS   : `vp fmt` (only when a package.json is present at the root)
# Notes:
#   - Don't pass `--exclude` to ruff: CLI replaces built-in defaults
#     (.venv, __pycache__, dist, build, ...). Excludes belong in pyproject.toml.
#   - Use `git ls-files -z | xargs -0 -r` for null-delimited, empty-safe pipes.
[group('Lint')]
fmt:
    @echo '🔧 Python (ruff format)...'
    uvx ruff format .
    @echo '🔧 Markdown (markdownlint-cli2 --fix)...'
    git ls-files -z '*.md' | xargs -0 -r mise x -- markdownlint-cli2 --fix
    @echo '🔧 JS/TS (vp fmt)...'
    @if [ -f package.json ]; then mise x -- vp fmt; else echo 'no package.json; skip'; fi
    @echo '✅ fmt done.'

# lint: report violations (auto-fixes where possible). Tool per language:
#   - Python  : ruff check --fix
#   - Shell   : shellcheck (no auto-fix)
#   - Markdown: markdownlint-cli2 --fix
#   - JS/TS   : vp lint
[group('Lint')]
lint:
    @echo '🔍 Python (ruff check --fix)...'
    uvx ruff check . --fix
    @echo '🔍 Shell (shellcheck)...'
    git ls-files -z '*.sh' | xargs -0 -r mise x -- shellcheck
    @echo '🔍 Markdown (markdownlint-cli2 --fix)...'
    git ls-files -z '*.md' | xargs -0 -r mise x -- markdownlint-cli2 --fix
    @echo '🔍 JS/TS (vp lint)...'
    @if [ -f package.json ]; then mise x -- vp lint; else echo 'no package.json; skip'; fi
    @echo '✅ lint done.'

# check: strict gate, never writes. Used by pre-push hook and CI.
[group('Lint')]
check:
    @echo '🔎 Python (ruff format --check)...'
    uvx ruff format --check .
    @echo '🔎 Python (ruff check, no --fix)...'
    uvx ruff check .
    @echo '🔎 Shell (shellcheck)...'
    git ls-files -z '*.sh' | xargs -0 -r mise x -- shellcheck
    @echo '🔎 Markdown (markdownlint-cli2)...'
    git ls-files -z '*.md' | xargs -0 -r mise x -- markdownlint-cli2
    @echo '🔎 JS/TS (vp check)...'
    @if [ -f package.json ]; then mise x -- vp check; else echo 'no package.json; skip'; fi
    @echo '🔎 Meta-semgrep rules against rule files...'
    uvx semgrep --config .semgrep/rules/meta/ --error .
    @echo '✅ All checks passed.'

# ------------------------------
# prek (j178/prek) — Rust reimplementation of pre-commit
# Install: just install-hooks  (== mise exec -- prek install)
# Run:     just pre-commit     (== mise exec -- prek run --all-files)
# ------------------------------

# Install prek-managed git hooks once per clone
[group('Lint')]
install-hooks:
    mise exec -- prek install

# Run every prek hook against all files (matches what git invokes pre-commit)
[group('Lint')]
pre-commit:
    mise exec -- prek run --all-files

# CI-equivalent gate: prek hooks plus the full sandbox test suite
[group('Lint')]
check-all: pre-commit check test
    @echo "✅ all checks passed"

# ------------------------------
# Add sets
# ------------------------------

# Add (all): install gcloud/brew/pnpm sets
[group('Add')]
add-all:
    just add-gcloud
    just add-brew
    just add-pnpm-g

# Add: install Homebrew bundle from dump/Brewfile (idempotent via brew bundle)
[group('Add')]
add-brew:
    #!/usr/bin/env bash
    set -euo pipefail
    brewfile="./dump/Brewfile"
    if [[ ! -s "$brewfile" ]]; then
        echo "❌ $brewfile is missing or empty"; exit 1
    fi
    (cd ./dump && brew bundle)

# Add: install gcloud components from dump/gcloud (skips already-installed)
[group('Add')]
add-gcloud:
    #!/usr/bin/env bash
    set -euo pipefail
    dump="./dump/gcloud"
    if [[ ! -s "$dump" ]]; then
        echo "❌ $dump is missing or empty"; exit 1
    fi
    installed=$(gcloud components list --filter='state.name=Installed' --format='value(id)' 2>/dev/null | sort -u)
    missing=$(comm -23 <(sort -u "$dump") <(echo "$installed"))
    if [[ -z "$missing" ]]; then
        echo "✅ all gcloud components in $dump are already installed"
        exit 0
    fi
    echo "📦 installing missing gcloud components:"
    echo "$missing" | sed 's/^/  - /'
    sudo gcloud components install --quiet $missing

# Add: install pnpm globals from dump/npm-global (skips already-installed)
[group('Add')]
add-pnpm-g:
    #!/usr/bin/env bash
    set -euo pipefail
    dump="./dump/npm-global"
    if [[ ! -s "$dump" ]]; then
        echo "❌ $dump is missing or empty"; exit 1
    fi
    # Strip trailing @version (keep scoped "@scope/name" intact)
    want=$(sed -E 's/(^.+)@[^@]+$/\1/' "$dump" | sort -u)
    # Use --json so only top-level deps are captured (parseable would include the .pnpm store too).
    installed=$(env -C "$HOME" pnpm ls -g --depth 0 --json 2>/dev/null | jq -r '.[0].dependencies | keys[]' | sort -u)
    missing=$(comm -23 <(echo "$want") <(echo "$installed"))
    if [[ -z "$missing" ]]; then
        echo "✅ all pnpm globals in $dump are already installed"
        exit 0
    fi
    echo "📦 installing missing pnpm globals:"
    echo "$missing" | sed 's/^/  - /'
    # pnpm refuses to run inside projects pinning packageManager; run from $HOME.
    env -C "$HOME" pnpm add --global $missing

# ------------------------------
# Update sets
# ------------------------------

# Update: pull latest for my submodules (skills, emulator, telemetry)
[group('Update')]
update-my-submodules:
    @echo "◆ Updating own submodules..."
    git submodule update --remote skills emulator telemetry
    @echo "✅ Submodules updated."

# Update (all): update gcloud/brew/pnpm and tools (pnpm safe mode)
[group('Update')]
update-all:
    just update-gcloud
    just update-brew
    just update-pnpm-g-safe
    @echo "◆ mise..."
    @if command -v mise >/dev/null 2>&1; then mise up && mise plugins up; else echo 'mise not found; skip'; fi
    @echo "◆ gh..."
    @if command -v gh >/dev/null 2>&1; then gh extension upgrade --all; else echo 'gh not found; skip'; fi
    @echo "◆ tldr..."
    @if command -v tldr >/dev/null 2>&1; then tldr --update; else echo 'tldr not found; skip'; fi
    @echo "◆ gitignore..."
    @if command -v git >/dev/null 2>&1 && git ignore --help >/dev/null 2>&1; then git ignore --update; else echo 'git ignore helper not found; skip'; fi
    @echo "◆ vscode extensions..."
    @if command -v code >/dev/null 2>&1; then code --update-extensions; else echo 'code not found; skip'; fi

# Update (all, safe): update pnpm individually; skip failures
[group('Update')]
update-all-safe:
    just update-gcloud
    just update-brew
    just update-pnpm-g-safe
    @echo "◆ mise..."
    @if command -v mise >/dev/null 2>&1; then mise up && mise plugins up; else echo 'mise not found; skip'; fi
    @echo "◆ gh..."
    @if command -v gh >/dev/null 2>&1; then gh extension upgrade --all; else echo 'gh not found; skip'; fi
    @echo "◆ tldr..."
    @if command -v tldr >/dev/null 2>&1; then tldr --update; else echo 'tldr not found; skip'; fi
    @echo "◆ gitignore..."
    @if command -v git >/dev/null 2>&1 && git ignore --help >/dev/null 2>&1; then git ignore --update; else echo 'git ignore helper not found; skip'; fi
    @echo "◆ vscode extensions..."
    @if command -v code >/dev/null 2>&1; then code --update-extensions; else echo 'code not found; skip'; fi

# Update: update and cleanup Homebrew
[group('Update')]
update-brew:
    @echo "◆ homebrew..."
    brew update && brew upgrade && brew cleanup

# Update: update gcloud components
[group('Update')]
update-gcloud:
    @echo "◆ gcloud..."
    sudo gcloud components update --quiet

# Update: update pnpm global packages
[group('Update')]
update-pnpm-g:
    @echo "◆ pnpm..."
    pnpm update --global

# Update: safely update pnpm globals (per-package; skip failures)
[group('Update')]
update-pnpm-g-safe:
    @echo "◆ pnpm(safe)..."
    @if command -v jq >/dev/null 2>&1; then \
      global_pkg_json="$(pnpm root -g 2>/dev/null)/../package.json"; \
      pkgs=$(jq -r '.dependencies | keys[]' "$$global_pkg_json" 2>/dev/null || true); \
      if [ -z "$$pkgs" ]; then echo 'No global packages found.'; exit 0; fi; \
      for p in $$pkgs; do echo "→ updating $$p"; pnpm add -g "$$p@latest" || echo "skip $$p"; done; \
    else \
      echo '⚠️ jq not found; falling back to pnpm update --global (best effort)'; \
      pnpm update --global || true; \
    fi
    pnpm store prune || true

# Repair: reset Homebrew state (rebase leftovers, inconsistencies)
[group('Setup')]
brew-repair:
    @echo '🔧 brew update-reset + doctor'
    brew update-reset
    brew update --force --quiet
    brew doctor || true

# ------------------------------
# Check sets
# ------------------------------

# Check: print PATH entries
[group('Check')]
check-path:
    # Check PATH
    @printf '%s\n' "$PATH" | tr ':' '\n'

# Check: show local IP addresses
[group('Check')]
check-myip:
    # Check my ip address
    @ifconfig | sed -En "s/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p"

# Check: list Docker containers' ports
[group('Check')]
check-dockerport:
    # Check docker port
    @ids=$(docker ps -q); \
    if [ -z "$ids" ]; then \
      echo '[]' | jq '.'; \
    else \
      echo "$ids" | xargs docker inspect | jq '.[] | {name: .Name, ports: .NetworkSettings.Ports}'; \
    fi

# Check: list installed Homebrew packages
[group('Check')]
check-brew:
    brew list

# Check: list gcloud components
[group('Check')]
check-gcloud:
    gcloud components list

# Check: list npm global packages
[group('Check')]
check-npm-g:
    npm ls --global --depth 0

# Check: list pnpm global packages
[group('Check')]
check-pnpm-g:
    pnpm list -g --depth=0

# Check: print rustc cfg
[group('Check')]
check-rust:
    rustc --print cfg
# ------------------------------
# Validation
# ------------------------------

# Validate: detect duplicate command names in PATH (order matters)
# Structural duplicates (brew-vs-system, mise-install-vs-shim, etc.) are ignored
# by design; only user-actionable duplicates are flagged.
[group('Validation')]
validate-path-duplicates:
    #!/usr/bin/env bash
    set -euo pipefail
    echo '🔎 Validating duplicate commands in PATH...'
    # Allow overriding scan targets with VALIDATE_PATH; fallback to current PATH
    scan_path="${VALIDATE_PATH:-$PATH}"
    IFS=':' read -r -a dirs <<< "$scan_path"
    shopt -s nullglob
    lines=()
    i=0
    for dir in "${dirs[@]}"; do
      [[ -d "$dir" ]] || continue
      i=$((i+1))
      for f in "$dir"/*; do
        [[ -f "$f" && -x "$f" ]] || continue
        name="$(basename "$f")"
        lines+=("$name $i $f")
      done
    done
    shopt -u nullglob
    if (( ${#lines[@]} == 0 )); then
      echo "✅ No duplicate command names across PATH"
      exit 0
    fi
    # Classify each path into a role. If ALL duplicate instances for a command
    # fall into "structural" roles, the duplicate is considered acceptable
    # (e.g. brew shadowing /usr/bin, mise-install paired with mise-shim).
    printf '%s\n' "${lines[@]}" | LC_ALL=C sort -k1,1 -k2,2n | awk -v home="$HOME" '
    function role(p,   r) {
      # mise layout (installs + shims)
      if (index(p, home "/.local/share/mise/installs/") == 1) return "structural"
      if (p == home "/.local/share/mise/shims" || index(p, home "/.local/share/mise/shims/") == 1) return "structural"
      # Homebrew (apple silicon) + opt/*/bin symlink farm + sbin
      if (index(p, "/opt/homebrew/bin/") == 1) return "structural"
      if (index(p, "/opt/homebrew/sbin/") == 1) return "structural"
      if (index(p, "/opt/homebrew/opt/") == 1) return "structural"
      # Homebrew cask bundle executables
      if (p ~ /^\/Applications\/[^\/]+\.app\/Contents\//) return "structural"
      # System paths (Apple default + cryptex + AppleInternal)
      if (index(p, "/usr/bin/") == 1) return "structural"
      if (index(p, "/bin/") == 1) return "structural"
      if (index(p, "/usr/sbin/") == 1) return "structural"
      if (index(p, "/sbin/") == 1) return "structural"
      if (index(p, "/System/") == 1) return "structural"
      if (index(p, "/Library/Apple/") == 1) return "structural"
      if (index(p, "/var/run/com.apple.") == 1) return "structural"
      # Nix profile layout
      if (index(p, home "/.nix-profile/bin/") == 1) return "structural"
      if (index(p, "/nix/var/nix/profiles/") == 1) return "structural"
      return "user"
    }
    {
      name=$1; idx=$2;
      path=$3;
      for (i=4; i<=NF; i++) path = path " " $i;
      if (NR==1) { prev=name; n=0 }
      if (name!=prev) {
        if (n>1) { emit() }
        n=0; prev=name
      }
      n++; rec[n]=idx ":" path; pr[n]=role(path)
    }
    END{
      if (n>1) { emit() }
      if (flagged>0) {
        print "⚠️  Found " flagged " user-actionable duplicate(s) in PATH"
        if (allowed>0) print "    (" allowed " structural duplicate(s) ignored)"
        exit 2
      } else {
        if (allowed>0) print "✅ No user-actionable duplicates (" allowed " structural duplicate(s) ignored)"
        else print "✅ No duplicate command names across PATH"
      }
    }
    function emit(   i, user_count) {
      user_count=0
      for (i=1;i<=n;i++) if (pr[i]=="user") user_count++
      if (user_count==0) { allowed++; return }
      print "command: " prev
      for (i=1;i<=n;i++) {
        tag = (pr[i]=="user") ? " [user]" : ""
        print "  " rec[i] tag
      }
      flagged++
    }'

# Doctor: environment diagnostics and guardrails
[group('Setup')]
doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    echo '🩺 Running environment doctor...'
    ok=0; warn=0; err=0
    log_ok(){ printf 'OK   %s%s\n' "$1" "${2:+ - $2}"; ok=$((ok+1)); }
    log_warn(){ printf 'WARN %s%s\n' "$1" "${2:+ - $2}"; warn=$((warn+1)); }
    log_err(){ printf 'ERR  %s%s\n' "$1" "${2:+ - $2}"; err=$((err+1)); }
    has(){ command -v "$1" >/dev/null 2>&1; }

    # Core
    if has bash; then log_ok 'bash' "$(bash --version | head -n1)"; else log_err 'bash' 'missing'; fi
    if has git; then log_ok 'git' "$(git --version 2>/dev/null || true)"; else log_err 'git' 'missing'; fi

    # Optional tools
    if has docker; then \
      if docker info >/dev/null 2>&1; then log_ok 'docker' 'daemon reachable'; else log_warn 'docker' 'cli present, daemon unreachable'; fi; \
    else log_warn 'docker' 'missing'; fi
    if has just; then log_ok 'just' "$(just --version 2>/dev/null || true)"; else log_warn 'just' 'missing'; fi
    if has uv; then log_ok 'uv' "$(uv --version 2>/dev/null || true)"; else log_warn 'uv' 'missing'; fi
    if has mise; then log_ok 'mise' "$(mise --version 2>/dev/null || true)"; else log_warn 'mise' 'missing'; fi
    if has brew; then log_ok 'brew' "$(brew --version | head -n1 2>/dev/null || true)"; else log_warn 'brew' 'missing'; fi
    if has gcloud; then log_ok 'gcloud' "$(gcloud --version 2>/dev/null | head -n1 || true)"; else log_warn 'gcloud' 'missing'; fi
    if has pnpm; then log_ok 'pnpm' "$(pnpm --version 2>/dev/null || true)"; else log_warn 'pnpm' 'missing'; fi
    if has npm; then log_ok 'npm' "$(npm --version 2>/dev/null || true)"; else log_warn 'npm' 'missing'; fi
    if has rustc; then log_ok 'rustc' "$(rustc --version 2>/dev/null || true)"; else log_warn 'rustc' 'missing'; fi

    # PATH duplicates (capture exit without aborting the script)
    set +e
    dup_out=$(just validate-path-duplicates 2>&1)
    rc=$?
    set -e
    case $rc in \
      0) log_ok 'PATH' 'no duplicate command names';; \
      2) log_warn 'PATH' 'duplicate command names found'; echo "$dup_out";; \
      *) log_warn 'PATH' 'validation error'; echo "$dup_out";; \
    esac

    echo "Doctor summary: ok=$ok warn=$warn err=$err"
    if [ "$err" -gt 0 ]; then exit 1; fi
    :

# ------------------------------
# Connect sets
# ------------------------------

# Connect: tunnel to Cloud SQL (cloud-sql-proxy v2)
[group('Connect')]
connect-gcloud-sql:
    # Requires env: GCLOUD_SQL_INSTANCE, LOCAL_SQL_PORT
    [[ -n "${GCLOUD_SQL_INSTANCE:-}" ]] || { echo 'ERROR: environment variable GCLOUD_SQL_INSTANCE not set'; exit 1; }
    [[ -n "${LOCAL_SQL_PORT:-}" ]] || { echo 'ERROR: environment variable LOCAL_SQL_PORT not set'; exit 1; }
    cloud-sql-proxy --port ${LOCAL_SQL_PORT} --private-ip ${GCLOUD_SQL_INSTANCE}

# Connect: start Azurite locally
[group('Connect')]
connect-azurite:
    azurite --silent --location .azurite --debug .azurite/debug.log

# ------------------------------
# Cloud sets
# ------------------------------

# List: gcloud configurations
[group('Cloud')]
gcloud-list:
    gcloud config configurations list

# List: Azure accounts
[group('Cloud')]
azure-list:
    az account list --output table

# List: AWS profiles
[group('Cloud')]
aws-list:
    aws configure list-profiles

# List: Dataform (BigQuery) tables, ELT (Extract, Load, Transform) not ETL (Extract, Transform, Load)
[group('Cloud')]
elt-list:
    dataform listtables bigquery

# ------------------------------
# Version checks
# ------------------------------

# Version check: verify NVCC version
[group('Check')]
check-version-nvcc expected:
    # Usage: just check-version-nvcc <EXPECTED_NVCC_VERSION>
    version=$(nvcc --version | sed -n 's/.*release \([0-9.]*\).*/\1/p' | head -n1); if [ "${version}" != "{{ expected }}" ]; then echo "ERROR: Expected NVCC version {{ expected }}, but found ${version}"; exit 1; fi

# Version check: verify PyTorch version
[group('Check')]
check-version-torch expected:
    # Usage: just check-version-torch <EXPECTED_TORCH_VERSION>
    version=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || true); if [ -z "${version}" ]; then echo "ERROR: PyTorch is not installed"; exit 1; elif [ "${version}" != "{{ expected }}" ]; then echo "ERROR: Expected PyTorch version {{ expected }}, but found ${version}"; exit 1; fi

# ------------------------------
# TLS checks
# ------------------------------

# Check: run local HTTPS server (Go) on port 443
# Access via https://localhost.hironow.dev/ (no port suffix required).
# Requires sudo for privileged port binding and to read the root-owned
# Let's Encrypt certificate files under private/certificates/live/.
[group('Check')]
check-localhost-tls port="443":
    sudo go run tools/simple-server/main.go -port {{ port }} -cert ./private/certificates/live/localhost.hironow.dev/fullchain.pem -key ./private/certificates/live/localhost.hironow.dev/privkey.pem -dir ./docs

[group('Validation')]
semgrep:
    uv run semgrep --config=auto .

# ------------------------------
# Claude Code
# ------------------------------

# Skills: manage Claude Code skills via bunx
# Usage: just skills ls              (default config)
#        just env=a skills ls -g     (env: p=personal, a/b/c=work)
env := ""

[group('Agents')]
skills *args:
    #!/usr/bin/env bash
    set -eu -o pipefail
    config_dir=""
    case "{{ env }}" in
      p) config_dir="$HOME/.claude" ;;
      a) config_dir="$HOME/.claude-work-a" ;;
      b) config_dir="$HOME/.claude-work-b" ;;
      c) config_dir="$HOME/.claude-work-c" ;;
      d) config_dir="$HOME/.claude-work-d" ;;
      "") ;;
      *) echo "ERROR: unknown env '{{ env }}'. Use: p, a, b, c, d"; exit 1 ;;
    esac
    if [ -n "$config_dir" ]; then
      CLAUDE_CONFIG_DIR="$config_dir" bunx skills {{ args }}
    else
      bunx skills {{ args }}
    fi

# CDP

# Start Chrome Dev with remote debugging
[group('CDP')]
start-cdp:
  @echo "Starting Chrome Dev with remote debugging on port 9222..."
  "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-dev-profile"

# Start Chrome Dev for debugging
[group('CDP')]
debug-cdp:
  @echo "Starting Chrome Dev for debugging with remote debugging on port 9222..."
  "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-debug-profile"

# ------------------------------
# DNS Tools
# ------------------------------

# DNS: lookup all records for a domain
[group('DNS')]
dns-lookup domain:
    @tools/dig-all.sh {{ domain }}

# DNS: compare records across public DNS servers (Google, Cloudflare, Quad9)
[group('DNS')]
dns-compare domain:
    @tools/dig-all.sh --compare {{ domain }}

# DNS: check migration readiness (compare live vs target nameserver)
[group('DNS')]
dns-migrate-check domain target_ns:
    @tools/dns-migration-check.sh {{ domain }} {{ target_ns }}

# DNS: check propagation status across global DNS servers
[group('DNS')]
dns-propagation domain:
    @tools/dns-migration-check.sh --propagation {{ domain }}

# DNS: scan for subdomain takeover vulnerabilities
[group('DNS')]
scan domain:
    subfinder -d {{ domain }} | httpx -silent | nuclei -tags takeover
    @echo "if you want check own subdomains, run: subfinder -d {{ domain }}"

# Check free before access network
[group('Check')]
check-free:
    @sudo lsof -i -P -n +c 0 | grep LISTEN | grep -vE "127.0.0.1|\[::1\]|ControlCenter|rapportd|symptomsd|launchd" | column -t


# Open docs and autoblogs in mo viewer (live-reload)
[group('Docs')]
docs-view:
    mo --clear --no-open
    mo --foreground -w 'docs/**/*.md' -w 'autoblogs/**/*.md'

# ------------------------------
# exe.hironow.dev — OpenTofu wrapper recipes
# ------------------------------
#
# All `exe-*` recipes operate on the tofu/exe stack. They:
#   1. cd tofu/exe
#   2. export TF_ENCRYPTION_PASSPHRASE from ~/.config/tofu/exe.passphrase
#      so state encryption is transparent.
#   3. require CLOUDFLARE_API_TOKEN and TAILSCALE_API_KEY in env
#      (the recipe fails fast if either is unset, with a hint).
#
# First-time setup before any `exe-*` recipe:
#   bash exe/scripts/bootstrap.sh
#   cp tofu/exe/terraform.tfvars.example tofu/exe/terraform.tfvars
#   $EDITOR tofu/exe/terraform.tfvars

# Run the bootstrap (idempotent): enable APIs, create state bucket, generate passphrase.
[group('Exe')]
exe-bootstrap:
    @bash exe/scripts/bootstrap.sh

# Build the TF_ENCRYPTION HCL payload from the local passphrase.
# State + plan encrypted with pbkdf2 + aes_gcm, enforced (no fallback).
# Mirrors the static block in tofu/exe/main.tf. HCL form (NOT JSON);
# JSON parsing is ambiguous in 1.11.
_exe-encryption:
    #!/usr/bin/env bash
    set -euo pipefail
    pass=$(cat "${HOME}/.config/tofu/exe.passphrase")
    cat <<EOF
    key_provider "pbkdf2" "default" {
      passphrase = "${pass}"
    }
    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }
    state {
      method   = method.aes_gcm.default
      enforced = true
    }
    plan {
      method   = method.aes_gcm.default
      enforced = true
    }
    EOF

# tofu init for the exe stack. (init talks only to the GCS backend
# and the provider registry; CF / TS API tokens are not required yet.)
[group('Exe')]
exe-init:
    #!/usr/bin/env bash
    set -euo pipefail
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu init

# tofu plan against the live state.
[group('Exe')]
exe-plan:
    #!/usr/bin/env bash
    set -euo pipefail
    : "$${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"
    : "$${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY before running}"
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu plan

# tofu apply (interactive — full plan).
[group('Exe')]
exe-apply:
    #!/usr/bin/env bash
    set -euo pipefail
    : "$${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"
    : "$${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY before running}"
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu apply

# Common targets:
#   just exe-replace google_compute_instance.exe_coder
#     # re-run startup-script after VM image / metadata changes
#   just exe-replace time_rotating.tailscale_keys
#     # force-rotate Tailscale auth keys
#   just exe-replace random_id.tunnel_secret
#     # rotate cloudflared tunnel credentials
# Force-replace one resource via tofu apply -replace=<target>.
[group('Exe')]
exe-replace target:
    #!/usr/bin/env bash
    set -euo pipefail
    : "$${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"
    : "$${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY before running}"
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu apply -replace={{ target }}

# tofu destroy of the VM only (keeps tunnel/secrets; cheap recreate).
[group('Exe')]
exe-down:
    #!/usr/bin/env bash
    set -euo pipefail
    : "$${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"
    : "$${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY before running}"
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu destroy \
      -target=google_compute_instance.exe_coder

# tofu destroy of every resource (VM, net, secrets, tunnel, DNS, Access).
[group('Exe')]
exe-down-all:
    #!/usr/bin/env bash
    set -euo pipefail
    : "$${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"
    : "$${TAILSCALE_API_KEY:?set TAILSCALE_API_KEY before running}"
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu destroy

# tofu fmt -check + provider-only init + validate. No state access; safe.
[group('Exe')]
exe-validate:
    #!/usr/bin/env bash
    set -euo pipefail
    cd tofu/exe
    tofu fmt -check -diff
    tofu init -backend=false -input=false >/dev/null
    tofu validate

# tofu output (JSON for scripts).
[group('Exe')]
exe-output *args:
    #!/usr/bin/env bash
    set -euo pipefail
    export TF_ENCRYPTION="$(just _exe-encryption)"
    cd tofu/exe && tofu output {{ args }}

# Post-deploy smoke checks (DNS, Access gate, VM state, secrets).
[group('Exe')]
exe-smoke:
    @bash exe/scripts/smoke.sh

# Staged destroy: stage=vm (default) | stack | nuke.
[group('Exe')]
exe-teardown stage="vm":
    @bash exe/scripts/teardown.sh {{ stage }}

# Run the startup-script e2e tests inside the Ubuntu 24.04 container.
# Catches keyring-path / installer-flag / 404 / dash-HOME / non-root
# postgres regressions BEFORE 'just exe-apply' burns 10 minutes on cloud.
[group('Exe')]
exe-test:
    uvx --with pytest pytest -v -m exe tests/exe/

# Symlink exe/scripts/cdr and cdr-header into ~/.local/bin.
#   cdr        : Coder CLI wrapper, injects CF Access service-token headers
#   cdr-header : same headers in 'key=value\n' form for the Coder VS Code
#                extension's 'Coder: Header Command' setting
[group('Exe')]
exe-cdr-install:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "${HOME}/.local/bin"
    for name in cdr cdr-header cdr-job; do
      src="$(pwd)/exe/scripts/$name"
      dst="${HOME}/.local/bin/$name"
      ln -sf "$src" "$dst"
      echo "✓ symlinked: $dst -> $src"
    done
    case ":$PATH:" in
      *":${HOME}/.local/bin:"*) ;;
      *) echo "  hint: add $${HOME}/.local/bin to PATH (e.g. in ~/.zshrc)" ;;
    esac
    echo "  first use:"
    echo "    cdr login https://exe.hironow.dev --token <CODER_API_TOKEN>"
    echo "    VS Code -> Settings -> Coder: Header Command ->"
    echo "      ${HOME}/.local/bin/cdr-header"
