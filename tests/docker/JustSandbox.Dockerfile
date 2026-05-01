ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE}

# Install required tools: bash, coreutils, network utils, git, curl, python.
# nodejs+npm are needed because mise.toml lists npm-backed tools
# (markdownlint-cli2, vp); without them `just install` fails to resolve.
#
# libc6-compat + gcompat: alpine ships musl libc, but several tools that
# expect glibc are dropped into the same dev container — most notably
# Coder's workspace agent ('./coder' inside an envbuilder-spawned
# Coder workspace). Without the compat shim, executing the glibc
# binary produces 'syntax error: unexpected newline' from sh trying
# to interpret the ELF as a script. Both packages are tiny.
#
# docker-cli: Coder workspace agent polls `docker ps` to discover
# DevContainer-mode children. The dockerd itself runs on the
# envbuilder VM host (debian-12); we just need the CLI inside the
# container so the agent's exec succeeds and the unix socket
# (bind-mounted by the workspace template) does the rest.
RUN apk add --no-cache \
    bash \
    coreutils \
    findutils \
    grep \
    sed \
    net-tools \
    curl \
    git \
    python3 \
    py3-pip \
    nodejs \
    npm \
    shellcheck \
    libc6-compat \
    gcompat \
    docker-cli

# Install latest just from GitHub releases (Alpine 3.19's just package is
# outdated and doesn't support [group()] syntax, which our justfile uses).
# We pin a specific version to avoid hitting GitHub API rate limits during
# repeated test runs and to keep builds reproducible.
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
      x86_64)  JUST_ARCH="x86_64-unknown-linux-musl" ;; \
      aarch64) JUST_ARCH="aarch64-unknown-linux-musl" ;; \
      *) echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac && \
    JUST_VERSION="1.40.0" && \
    curl -fsSL "https://github.com/casey/just/releases/download/${JUST_VERSION}/just-${JUST_VERSION}-${JUST_ARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin just

# Install sheldon (zsh plugin manager) - download pre-built binary.
# Version is pinned to avoid GitHub API rate limits during builds.
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
      x86_64)  SHELDON_ARCH="x86_64-unknown-linux-musl" ;; \
      aarch64) SHELDON_ARCH="aarch64-unknown-linux-musl" ;; \
      *) echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac && \
    SHELDON_VERSION="0.8.4" && \
    curl -fsSL "https://github.com/rossmacarthur/sheldon/releases/download/${SHELDON_VERSION}/sheldon-${SHELDON_VERSION}-${SHELDON_ARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin

ENV HOME=/root
WORKDIR /root/dotfiles

# Install uv for Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install mise (rtx-style tool manager). Used by `just install`, `just lint-md`,
# and the shellcheck step in `just lint`. We install the binary only here;
# the `just install` test below covers exercising `mise install` itself.
RUN curl -fsSL https://mise.run | sh
ENV PATH="/root/.local/bin:/root/.local/share/mise/shims:$PATH"

# Copy repository contents into container (sandboxed workspace)
COPY . /root/dotfiles

# Pre-provision all tools listed in mise.toml at image build time. Must come
# AFTER the COPY so mise can read mise.toml. This:
#   1. prevents tests from being throttled by GitHub API rate limits when
#      `mise install` runs at test time (each `latest` resolution = 1 API hit)
#   2. records concrete versions in mise.lock so MISE_OFFLINE=1 at test time
#      can reuse the installed binaries without re-querying GitHub
# Both are pre-conditions for stable container-based recipe coverage.
#
# `--mount=type=secret,id=github_token` lets the CI runner pass GITHUB_TOKEN
# without baking it into the image. Without auth mise hits the 60-req/hr
# unauthenticated GitHub API limit and the build fails on shared CI IPs.
# Locally the secret is absent and the unauthenticated fetch is enough.
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then \
      export GITHUB_TOKEN="$(cat /run/secrets/github_token)"; \
    fi && \
    mise trust mise.toml && touch mise.lock && mise install

# Provide stub for nvcc with a realistic version string
RUN printf '#!/bin/sh\necho "Cuda compilation tools, release 12.3, V12.3.52"\n' > /usr/local/bin/nvcc \
    && chmod +x /usr/local/bin/nvcc

# Ensure tools are on PATH and basic sanity
RUN just --version && bash --version | head -n1 && python3 --version && uv --version
