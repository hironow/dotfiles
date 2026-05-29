# https://just.systems

default: help

# List available tasks
help:
    @just --list --unsorted

MARKDOWNLINT := "bunx markdownlint-cli2"


# Update dependencies with uv
update:
    @echo 'Updating...'
    uv lock --upgrade
    uv sync
    @echo 'Updated.'

# Test pytest
test path='tests/' opts='-v':
    @echo '🧪 Running tests via uv: pytest' '{{path}}' '{{opts}}'
    uv run pytest '{{path}}' '{{opts}}'
    @echo '✅ Tests finished.'

# Fast tests (exclude e2e)
test-fast:
    @bash scripts/run-tests-fast.sh

# E2E tests only
test-e2e:
    @bash scripts/run-tests-e2e.sh

# Pre-build selected images
prebuild images='a2a-inspector firebase-emulator mcp-inspector postgres':
    @bash scripts/prebuild-images.sh {{images}}

# Start services (detached)
up nobuild='no':
    @if [ "{{nobuild}}" = 'yes' ]; then \
        bash scripts/start-services.sh --no-build; \
    else \
        bash scripts/start-services.sh; \
    fi

# Wait for services
wait default='30' a2a='60' mcp='60' postgres='60':
    @bash scripts/wait-for-services.sh --default {{default}} --a2a {{a2a}} --mcp {{mcp}} --postgres {{postgres}}

# Clean up volumes (use with caution - deletes all data)
clean-volumes:
    @echo '⚠️  Cleaning up Docker volumes...'
    docker compose down -v || true
    @echo '✅ Volumes cleaned.'

# One-shot: prebuild -> up -> wait
start:
    @echo '🧹 Cleaning up old volumes...'
    @docker compose down -v || true
    @bash scripts/prebuild-images.sh a2a-inspector firebase-emulator mcp-inspector postgres
    @bash scripts/start-services.sh
    @bash scripts/wait-for-services.sh --default 30 --a2a 60 --mcp 60 --postgres 60

# Stop emulators (with Firebase export)
stop:
    @bash scripts/stop-services.sh

# Show emulator status (containers + endpoints)
check:
    @bash scripts/check-status.sh

# Check port usage before starting emulators
port-check:
    #!/usr/bin/env bash
    echo '🔍 Checking port usage...'
    for port in 9099 8080 8086 9010 9020 55432 7474 7687 8081 6274 5252 6333 6334 5433 9200 9300; do
        result=$(witr --port $port --short 2>/dev/null)
        if [ -n "$result" ]; then
            echo "⚠️  Port $port: $result"
        fi
    done
    echo '✅ Port check finished.'

# Verify PostgreSQL 18 basics (version, uuidv7 availability)
pg-verify:
    @bash scripts/verify-postgres18.sh

# Check gcloud auth (detailed + strict)
gcloud-auth-check:
    @bash scripts/check-gcloud-auth.sh --details --strict --verbose

# Format
format path='tests/':
    @echo '🔧 Formatting Python with ruff...'
    uv run ruff format '{{path}}'
    @echo '🪄 Formatting Go CLIs with go fmt (if available)...'
    @if command -v go >/dev/null 2>&1; then \
        set -e; \
        for dir in pgadapter-cli neo4j-cli elasticsearch-cli qdrant-cli bigtable-cli postgres-cli; do \
          if [ -f "$dir/go.mod" ]; then \
            echo '  •' "$dir"; \
            (cd "$dir" && go fmt ./...); \
          fi; \
        done; \
        echo '✅ Go formatted.'; \
      else \
        echo '⚠️  go not found; skipping go fmt'; \
      fi
    @echo '✅ Formatting finished.'

# Lint
lint path='tests/' opts='--fix':
    @echo '🔍 Linting code with ruff...'
    uv run ruff check '{{path}}' '{{opts}}'
    @echo 'Semgrep linting...'
    uv run semgrep --config .semgrep/ --error
    @echo 'markdown linting...'
    {{MARKDOWNLINT}} --fix "**/*.md"
    @echo '✅ Linting finished.'

# Lint check (no auto-fix, for CI)
lint-check path='tests/':
    @echo '🔍 Checking code with ruff...'
    uv run ruff check '{{path}}'
    @echo 'Semgrep checking...'
    uv run semgrep --config .semgrep/ --error
    @echo 'markdown checking...'
    {{MARKDOWNLINT}} "**/*.md"
    @echo '✅ Lint check finished.'


# ---- WRKFLW helpers ----

# Validate workflows with wrkflw
[group("wrkflw")]
gh-validate target='':
    @if ! command -v wrkflw >/dev/null 2>&1; then \
        echo '❌ wrkflw not found.'; \
        echo '   Install with: cargo install wrkflw'; \
        exit 127; \
    fi
    @if [ -n "{{target}}" ]; then \
        echo '🔎 Validating workflow:' '{{target}}'; \
        wrkflw validate "{{target}}"; \
    else \
        echo '🔎 Validating workflows in .github/workflows'; \
        wrkflw validate; \
    fi

# Check wrkflw availability and show version
[group("wrkflw")]
gh-check:
    @if command -v wrkflw >/dev/null 2>&1; then \
        echo '✅ wrkflw installed:'; wrkflw --version || wrkflw -V || true; \
    else \
        echo '❌ wrkflw not found. Install with: cargo install wrkflw'; \
        exit 127; \
    fi
