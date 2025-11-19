# https://just.systems

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default: show help
default: help

# Help: list available recipes
help:
    @just --list --unsorted

# ------------------------------
# Project Management
# ------------------------------

# Install: setup tools via mise
install:
    # Install tools via mise (versions are managed in mise.toml)
    mise install

# Deploy: symlink dotfiles to home (~/.zshrc)
deploy:
    @echo "==> Start to deploy dotfiles to home directory."
    ln -sf ~/dotfiles/.zshrc ~/.zshrc

# Clean: remove deployed dotfiles (~/.zshrc)
clean:
    @echo "==> Remove dotfiles in your home directory..."
    rm -vrf ~/.zshrc

# Dump: write Homebrew bundle into dump/
dump:
    # Dump current brew bundle
    rm -f ./dump/Brewfile && (cd ./dump && brew bundle dump)

# Freeze: pin Python deps to requirements.txt (uv)
freeze:
    # Freeze current python packages using uv
    uv pip freeze | uv pip compile - -o requirements.txt

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

# Self-check: quick, safe health checks with summary
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

# Format: run ruff format via uvx
ruff-format path="." opts="":
    @echo '🔧 Formatting with ruff via uvx...'
    uvx ruff format '{{ path }}' {{ opts }}
    @echo '✅ Formatting done.'

# Lint: run ruff check via uvx
ruff-check path="." opts="":
    @echo '🔍 Checking with ruff via uvx...'
    uvx ruff check '{{ path }}' {{ opts }}
    @echo '✅ Check done.'

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
      pkgs=$(pnpm list -g --depth 0 --json | jq -r '.[0].dependencies | keys[]' 2>/dev/null || true); \
      if [ -z "$$pkgs" ]; then echo 'No global packages found.'; exit 0; fi; \
      for p in $$pkgs; do echo "→ updating $$p"; pnpm add -g "$$p@latest" || echo "skip $$p"; done; \
    else \
      echo '⚠️ jq not found; falling back to pnpm update --global (best effort)'; \
      pnpm update --global || true; \
    fi
    pnpm store prune || true

# Repair: reset Homebrew state (rebase leftovers, inconsistencies)
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

# Check: list Watchman watch roots (and pid)
check-watchman:
    @bash scripts/watchman-status.sh

# ------------------------------
# Validation
# ------------------------------

# Validate: detect duplicate command names in PATH (order matters)
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
    printf '%s\n' "${lines[@]}" | LC_ALL=C sort -k1,1 -k2,2n | awk '
    {
      name=$1; idx=$2;
      $1=""; $2="";
      sub(/^  */,"",$0);
      if (NR==1) { prev=name; n=0 }
      if (name!=prev) {
        if (n>1) {
          print "command: " prev;
          for (i=1;i<=n;i++) print "  " rec[i]
          dup++
        }
        n=0; prev=name
      }
      n++; rec[n]=idx ":" $0
    }
    END{
      if (n>1) {
        print "command: " prev;
        for (i=1;i<=n;i++) print "  " rec[i]
        dup++
      }
      if (dup>0) {
        print "⚠️  Found " dup " command(s) shadowed by PATH order"
        exit 2
      } else {
        print "✅ No duplicate command names across PATH"
      }
    }'

# Doctor: environment diagnostics and guardrails
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

# Connect: tunnel to Cloud SQL (cloud_sql_proxy)
connect-gcloud-sql:
    # Requires env: GCLOUD_SQL_INSTANCE, LOCAL_SQL_PORT
    [[ -n "${GCLOUD_SQL_INSTANCE:-}" ]] || { echo 'ERROR: environment variable GCLOUD_SQL_INSTANCE not set'; exit 1; }
    [[ -n "${LOCAL_SQL_PORT:-}" ]] || { echo 'ERROR: environment variable LOCAL_SQL_PORT not set'; exit 1; }
    cloud_sql_proxy -instances=${GCLOUD_SQL_INSTANCE}=tcp:${LOCAL_SQL_PORT}

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

# List: Dataform (BigQuery) tables
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

# Check: run local HTTPS server (Go)
check-localhost-tls:
    # Serve TLS on localhost using the Go simple-server
    mise x -- sudo go run tools/simple-server/main.go
