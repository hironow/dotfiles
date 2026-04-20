# https://just.systems

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default: show help
default: help

# Help: list available recipes
help:
    @just --list --unsorted

# Define specific commands
MARKDOWNLINT := "bun x markdownlint-cli2"
PDOC := "uv run pdoc"

lint-md:
    @{{MARKDOWNLINT}} --fix "docs/**/*.md" "README.md" "experiments/**/*.md" "!submodules/**" "!sets/**" "!input/**" "!output/**"

pdoc port="8888" pkg=".":
    {{PDOC}} --port {{port}} {{pkg}}


# ------------------------------
# Project Management
# ------------------------------

# Run meta semgrep rules against rule files (ROOT_AGENTS.md etc.)
meta-semgrep:
    semgrep --config .semgrep/rules/meta/ --error .

# Verify meta rules themselves with their test annotations
meta-semgrep-test:
    semgrep --test --config .semgrep/rules/meta/

# Full validation of rule files
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
[group('Setup')]
sync-agents:
    @uv run scripts/sync_agents.py

# Sync (preview): show what would be synced without making changes
[group('Setup')]
sync-agents-preview:
    @uv run scripts/sync_agents.py --preview

# Sync (auto): sync all without prompts
[group('Setup')]
sync-agents-auto:
    @uv run scripts/sync_agents.py --yes

# Sync (override): full replace — dotfiles wins, orphans removed, no prompts
[group('Setup')]
sync-agents-override:
    @uv run scripts/sync_agents.py --override

# Sync (orphans): show target-only items that would be removed
[group('Setup')]
sync-agents-orphans:
    @uv run scripts/sync_agents.py --orphans

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
[group('Setup')]
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
    # Dump installed gcloud components (restore with: gcloud components install $(cat dump/gcloud))
    gcloud components list --filter='state.name=Installed' --format='value(id)' 2>/dev/null | sort -u > ./dump/gcloud


# ------------------------------
# Tests
# ------------------------------

# Test: build sandbox (if available) and run pytest (verbose)
test:
    @echo '🧪 Preparing Docker sandbox (if available)...'
    @if command -v docker >/dev/null 2>&1; then \
    	echo '→ docker detected; building sandbox image'; \
    	docker build -t dotfiles-just-sandbox:latest -f tests/docker/JustSandbox.Dockerfile . || echo '⚠️ sandbox build failed (tests may skip)'; \
    else \
    	echo '⚠️ docker not found; tests may skip'; \
    fi
    @echo '🧪 Running pytest (verbose with skip reasons)...'
    uvx pytest -v -ra tests/test_just_sandbox.py
    @echo '✅ Tests finished.'

# Test (install): run install.sh verification in Docker
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
test-mark marker="":
    @echo '🧪 Running pytest with marker:' '{{ marker }}'
    @if [ -n "{{ marker }}" ]; then \
    	uvx pytest -v -ra -m '{{ marker }}' tests/test_just_sandbox.py; \
    else \
    	echo 'Marker is empty. Usage: just test-mark marker=install'; \
    	exit 2; \
    fi

# ------------------------------
# Formatting
# ------------------------------

# Format: run all formatters (Python, Prettier)
format:
    @echo '🔧 Formatting Python (ruff)...'
    uvx ruff format . --exclude emulator
    @echo '🔧 Formatting others (prettier)...'
    git ls-files | grep -vE '^(emulator$|emulator/|ROOT_AGENTS\.md$)' | xargs mise x -- prettier --write --ignore-unknown
    @echo '✅ Format done.'

# Lint: run all linters (Python, Shell, Prettier)
lint:
    @echo '🔍 Linting Python (ruff)...'
    uvx ruff check . --fix --exclude emulator
    @echo '🔍 Linting Shell (shellcheck)...'
    git ls-files '*.sh' | grep -vE '^(emulator$|emulator/)' | xargs mise x -- shellcheck
    @echo '🔍 Checking others (prettier)...'
    git ls-files | grep -vE '^(emulator$|emulator/|ROOT_AGENTS\.md$)' | xargs mise x -- prettier --check --ignore-unknown
    @echo '✅ Lint done.'

# ------------------------------
# Add sets
# ------------------------------

# Add (all): install gcloud/brew/pnpm sets
add-all:
    just add-gcloud
    just add-brew
    just add-pnpm-g

# Add: install Homebrew bundle
add-brew:
    # Install brew bundle
    (cd ./dump && brew bundle)

# Add: install gcloud components
add-gcloud:
    # Install gcloud components
    sudo gcloud components install $(awk '{ORS=" "} {print}' ./dump/gcloud)

# Add: install pnpm global packages
add-pnpm-g:
    # Install pnpm global packages
    pnpm add --global $(awk '{ORS=" "} {print}' ./dump/npm-global)

# ------------------------------
# Update sets
# ------------------------------

# Update: pull latest for my submodules (skills, emulator, telemetry)
update-my-submodules:
    @echo "◆ Updating own submodules..."
    git submodule update --remote skills emulator telemetry
    @echo "✅ Submodules updated."

# Update (all): update gcloud/brew/pnpm and tools (pnpm safe mode)
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
update-brew:
    @echo "◆ homebrew..."
    brew update && brew upgrade && brew cleanup

# Update: update gcloud components
update-gcloud:
    @echo "◆ gcloud..."
    sudo gcloud components update --quiet

# Update: update pnpm global packages
update-pnpm-g:
    @echo "◆ pnpm..."
    pnpm update --global

# Update: safely update pnpm globals (per-package; skip failures)
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
check-path:
    # Check PATH
    @printf '%s\n' "$PATH" | tr ':' '\n'

# Check: show local IP addresses
check-myip:
    # Check my ip address
    @ifconfig | sed -En "s/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p"

# Check: list Docker containers' ports
check-dockerport:
    # Check docker port
    @ids=$(docker ps -q); \
    if [ -z "$ids" ]; then \
      echo '[]' | jq '.'; \
    else \
      echo "$ids" | xargs docker inspect | jq '.[] | {name: .Name, ports: .NetworkSettings.Ports}'; \
    fi

# Check: list installed Homebrew packages
check-brew:
    brew list

# Check: list gcloud components
check-gcloud:
    gcloud components list

# Check: list npm global packages
check-npm-g:
    npm ls --global --depth 0

# Check: list pnpm global packages
check-pnpm-g:
    pnpm list -g --depth=0

# Check: print rustc cfg
check-rust:
    rustc --print cfg
# ------------------------------
# Validation
# ------------------------------

# Validate: detect duplicate command names in PATH (order matters)
# Structural duplicates (brew-vs-system, mise-install-vs-shim, etc.) are ignored
# by design; only user-actionable duplicates are flagged.
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
connect-gcloud-sql:
    # Requires env: GCLOUD_SQL_INSTANCE, LOCAL_SQL_PORT
    [[ -n "${GCLOUD_SQL_INSTANCE:-}" ]] || { echo 'ERROR: environment variable GCLOUD_SQL_INSTANCE not set'; exit 1; }
    [[ -n "${LOCAL_SQL_PORT:-}" ]] || { echo 'ERROR: environment variable LOCAL_SQL_PORT not set'; exit 1; }
    cloud-sql-proxy --port ${LOCAL_SQL_PORT} --private-ip ${GCLOUD_SQL_INSTANCE}

# Connect: start Azurite locally
connect-azurite:
    azurite --silent --location .azurite --debug .azurite/debug.log

# ------------------------------
# Cloud sets
# ------------------------------

# List: gcloud configurations
gcloud-list:
    gcloud config configurations list

# List: Azure accounts
azure-list:
    az account list --output table

# List: AWS profiles
aws-list:
    aws configure list-profiles

# List: Dataform (BigQuery) tables, ELT (Extract, Load, Transform) not ETL (Extract, Transform, Load)
elt-list:
    dataform listtables bigquery

# ------------------------------
# Version checks
# ------------------------------

# Version check: verify NVCC version
check-version-nvcc expected:
    # Usage: just check-version-nvcc <EXPECTED_NVCC_VERSION>
    version=$(nvcc --version | sed -n 's/.*release \([0-9.]*\).*/\1/p' | head -n1); if [ "${version}" != "{{ expected }}" ]; then echo "ERROR: Expected NVCC version {{ expected }}, but found ${version}"; exit 1; fi

# Version check: verify PyTorch version
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
check-localhost-tls port="443":
    sudo go run tools/simple-server/main.go -port {{ port }} -cert ./private/certificates/live/localhost.hironow.dev/fullchain.pem -key ./private/certificates/live/localhost.hironow.dev/privkey.pem -dir ./docs

semgrep:
    uv run semgrep --config=auto .

# ------------------------------
# Claude Code
# ------------------------------

# Skills: manage Claude Code skills via bunx
# Usage: just skills ls              (default config)
#        just env=a skills ls -g     (env: p=personal, a/b/c=work)
env := ""

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
start-cdp:
  @echo "Starting Chrome Dev with remote debugging on port 9222..."
  "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-dev-profile"

# Start Chrome Dev for debugging
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
check-free:
    @sudo lsof -i -P -n +c 0 | grep LISTEN | grep -vE "127.0.0.1|\[::1\]|ControlCenter|rapportd|symptomsd|launchd" | column -t


# Open docs and autoblogs in mo viewer (live-reload)
docs-view:
    mo --clear --no-open
    mo --foreground -w 'docs/**/*.md' -w 'autoblogs/**/*.md'
