ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE}

# Install required tools: bash, coreutils, network utils, just, git, curl
RUN apk add --no-cache \
    bash \
    coreutils \
    findutils \
    grep \
    sed \
    net-tools \
    curl \
    git \
    just

ENV HOME=/root
WORKDIR /root/dotfiles

# Copy repository contents into container (sandboxed workspace)
COPY . /root/dotfiles

# Provide stub for nvcc with a realistic version string
RUN printf '#!/bin/sh\necho "Cuda compilation tools, release 12.3, V12.3.52"\n' > /usr/local/bin/nvcc \
    && chmod +x /usr/local/bin/nvcc

# Ensure just is on PATH and basic sanity
RUN just --version && bash --version | head -n1
