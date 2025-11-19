FROM ubuntu:22.04

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash testuser
USER testuser
WORKDIR /home/testuser

# Prepare "remote" repo
RUN mkdir -p /tmp/dotfiles-repo
COPY --chown=testuser:testuser . /tmp/dotfiles-repo

# Initialize git in the "remote" repo so it can be cloned
RUN cd /tmp/dotfiles-repo && \
    git init -b main && \
    git config user.email "test@example.com" && \
    git config user.name "Test User" && \
    git add . && \
    git commit -m "Initial commit"

# Set environment variables
ENV INSTALL_SKIP_HOMEBREW=1
ENV INSTALL_SKIP_GCLOUD=1
ENV INSTALL_SKIP_ADD_UPDATE=1
ENV DOTFILES_REPO=/tmp/dotfiles-repo

# Run install.sh from the "remote" source
# This should clone from DOTFILES_REPO to $HOME/dotfiles and run setup
RUN bash /tmp/dotfiles-repo/install.sh

# Add .local/bin to PATH for subsequent commands
ENV PATH="/home/testuser/.local/bin:$PATH"

# Verify just is installed in .local/bin
RUN test -x ~/.local/bin/just && \
    just --version

# Verify zgen update logic (second run)
# Create a dummy zgen dir to test update
RUN mkdir -p ~/.zgen && \
    cd ~/.zgen && \
    git init && \
    git config user.email "test@example.com" && \
    git config user.name "Test User" && \
    git commit --allow-empty -m "Initial zgen"

# Run install.sh again to test update paths
RUN bash /tmp/dotfiles-repo/install.sh
