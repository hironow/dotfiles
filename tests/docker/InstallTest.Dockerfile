FROM docker.io/library/ubuntu:26.04

# Provision native CLI/network/storage packages as root, never a Podman machine.
# The ordinary installer below must succeed without sudo authorization.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    sudo \
    podman \
    netavark \
    aardvark-dns \
    passt \
    uidmap \
    fuse-overlayfs \
    && podman --version \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash testuser
USER testuser
ENV HOME=/home/testuser
WORKDIR /home/testuser

# Tripwire: both normal setup runs may probe the real CLI version only.
# Any machine/service/container operation fails the acceptance image build.
RUN mkdir -p "$HOME/test-bin" && \
    printf '%s\n' '#!/bin/sh' \
      '[ "$#" -eq 1 ] && [ "$1" = --version ] || { echo "Unexpected Podman operation" >&2; exit 91; }' \
      'printf "%s\n" "$*" >> "$HOME/podman-provisioning-calls"' \
      'exec /usr/bin/podman "$@"' > "$HOME/test-bin/podman" && \
    chmod +x "$HOME/test-bin/podman"
ENV PATH="/home/testuser/test-bin:/home/testuser/.local/bin:$PATH"

# Prepare "remote" repo
RUN mkdir -p /tmp/dotfiles-repo
COPY --chown=testuser:testuser . /tmp/dotfiles-repo

# Initialize git in the "remote" repo so it can be cloned
RUN cd /tmp/dotfiles-repo && \
    git init -b main && \
    git config user.email "test@example.com" && \
    git config user.name "Test User" && \
    git config commit.gpgsign false && \
    git add . && \
    git commit -m "Initial commit"

# Set environment variables
ENV INSTALL_SKIP_HOMEBREW=1
ENV INSTALL_SKIP_GCLOUD=1
ENV INSTALL_SKIP_ADD_UPDATE=1
# A file:// URL makes git clone through its transport instead of hardlinking
# objects; hardlinks across image layers fail with "hardlink different from source".
ENV DOTFILES_REPO=file:///tmp/dotfiles-repo

# Fresh acceptance nonce invalidates setup layers, not earlier package layers.
ARG DOTFILES_INSTALL_ACCEPTANCE_RUN
# Run install.sh from the "remote" source, then emit current-run evidence.
RUN test -n "$DOTFILES_INSTALL_ACCEPTANCE_RUN" && \
    bash /tmp/dotfiles-repo/install.sh && \
    printf 'DOTFILES_INSTALL_PASS1:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"

# Add .local/bin to PATH for subsequent commands
ENV PATH="/home/testuser/.local/bin:$PATH"

# Verify just is installed in .local/bin
RUN test -x ~/.local/bin/just && \
    just --version

# A fresh install fetches no zsh plugin manager; sheldon loads the plugins.
RUN test ! -e "$HOME/.zgen"

# Machines set up while .zshrc still loaded zgen can keep a ~/.zgen that is
# not a git checkout (only an old plugin cache). The update run must leave it alone.
RUN mkdir -p ~/.zgen/robbyrussell && \
    touch ~/.zgen/robbyrussell/keep

# Run install.sh again to test update paths. Synthetic fixture commits above
# never require the operator's private signing keys or host git configuration.
RUN bash /tmp/dotfiles-repo/install.sh && \
    test -f ~/.zgen/robbyrussell/keep && \
    printf 'DOTFILES_INSTALL_PASS2:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"
RUN test "$(wc -l < "$HOME/podman-provisioning-calls")" -eq 2 && \
    test "$(sort -u "$HOME/podman-provisioning-calls")" = --version && \
    printf 'DOTFILES_INSTALL_TRIPWIRE:%s\n' "$DOTFILES_INSTALL_ACCEPTANCE_RUN"
