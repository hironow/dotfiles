FROM ubuntu:22.04

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    sudo \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Prepare "remote" repo
RUN mkdir -p /tmp/dotfiles-repo
COPY . /tmp/dotfiles-repo

# Initialize git in the "remote" repo so it can be cloned
RUN cd /tmp/dotfiles-repo && \
    git init -b main && \
    git config user.email "test@example.com" && \
    git config user.name "Test User" && \
    git add . && \
    git commit -m "Initial commit"

# Set environment variables — skip Homebrew, gcloud, and post-install steps
# Nix and Home Manager ARE exercised (they are the point of this test)
ENV DOTFILES_REPO=/tmp/dotfiles-repo
ENV INSTALL_SKIP_HOMEBREW=1
ENV INSTALL_SKIP_GCLOUD=1
ENV INSTALL_SKIP_ADD_UPDATE=1

# Run install.sh (installs Nix + applies Home Manager as root)
RUN bash /tmp/dotfiles-repo/install.sh

# Verify Nix is installed
RUN . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh && nix --version

# Verify dotfile symlinks are created by Home Manager
RUN test -L ~/.zshrc
RUN test -L ~/.config/starship.toml
RUN test -L ~/.tmux.conf

# Verify idempotency (second run)
RUN bash /tmp/dotfiles-repo/install.sh
