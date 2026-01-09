ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE}

# Install required tools: bash, coreutils, network utils, git, curl, python
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
    py3-pip

# Install latest just (Alpine package is outdated and doesn't support [group()] syntax)
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install sheldon (zsh plugin manager) - download pre-built binary
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then SHELDON_ARCH="x86_64-unknown-linux-musl"; \
    elif [ "$ARCH" = "aarch64" ]; then SHELDON_ARCH="aarch64-unknown-linux-musl"; \
    else echo "Unsupported arch: $ARCH" && exit 1; fi && \
    SHELDON_VERSION=$(curl -fsSL https://api.github.com/repos/rossmacarthur/sheldon/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/') && \
    curl -fsSL "https://github.com/rossmacarthur/sheldon/releases/download/${SHELDON_VERSION}/sheldon-${SHELDON_VERSION}-${SHELDON_ARCH}.tar.gz" | tar -xz -C /usr/local/bin

ENV HOME=/root
WORKDIR /root/dotfiles

# Install uv for Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy repository contents into container (sandboxed workspace)
COPY . /root/dotfiles

# Provide stub for nvcc with a realistic version string
RUN printf '#!/bin/sh\necho "Cuda compilation tools, release 12.3, V12.3.52"\n' > /usr/local/bin/nvcc \
    && chmod +x /usr/local/bin/nvcc

# Ensure tools are on PATH and basic sanity
RUN just --version && bash --version | head -n1 && python3 --version && uv --version
