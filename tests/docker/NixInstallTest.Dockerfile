FROM ubuntu:22.04

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    sudo \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user with sudo
RUN useradd -m -s /bin/bash testuser && \
    echo "testuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
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

# Set environment variables — skip Homebrew, gcloud, and post-install steps
ENV INSTALL_SKIP_HOMEBREW=1
ENV INSTALL_SKIP_GCLOUD=1
ENV INSTALL_SKIP_ADD_UPDATE=1
ENV DOTFILES_REPO=/tmp/dotfiles-repo

# Run install.sh from the "remote" source
RUN bash /tmp/dotfiles-repo/install.sh

# Verify Nix is installed
RUN . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh && nix --version

# Verify dotfile symlinks are created by Home Manager
RUN test -L ~/.zshrc
RUN test -L ~/.config/starship.toml

# Verify idempotency (second run)
RUN bash /tmp/dotfiles-repo/install.sh
