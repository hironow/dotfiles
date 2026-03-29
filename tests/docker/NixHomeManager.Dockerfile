FROM nixos/nix:latest

# Enable flakes, nix-command, and disable sandbox (Docker handles isolation)
RUN mkdir -p /etc/nix && printf 'experimental-features = nix-command flakes\nsandbox = false\n' > /etc/nix/nix.conf

WORKDIR /root/dotfiles

# Copy repository contents
COPY . /root/dotfiles

# Remove pre-installed nix-env packages that conflict with Home Manager
# Keep nix and nss-cacert (SSL certs needed for downloads)
RUN for pkg in $(nix-env -q | grep -vE '^nix-|^nss-cacert'); do nix-env -e "$pkg" || true; done

# Detect system and build Home Manager configuration
RUN SYSTEM=$(nix eval --raw --impure --expr 'builtins.currentSystem') && \
    echo "Building for system: $SYSTEM" && \
    nix run home-manager -- switch --flake ".#root@${SYSTEM}" --impure --print-build-logs

# Verify: key packages installed (use command -v since 'which' may not exist)
RUN command -v git && command -v fzf && command -v rg && command -v starship && \
    command -v sheldon && command -v tmux && command -v just && command -v jq && \
    command -v bat && command -v fd

# Verify: dotfile symlinks
RUN test -L ~/.zshrc
RUN test -L ~/.config/sheldon/plugins.toml
RUN test -L ~/.config/starship.toml
RUN test -L ~/.tmux.conf
RUN test -L ~/.config/ghostty/config
RUN test -f ~/.config/git/ignore

# Verify: idempotency (second run succeeds)
RUN SYSTEM=$(nix eval --raw --impure --expr 'builtins.currentSystem') && \
    nix run home-manager -- switch --flake ".#root@${SYSTEM}" --impure

RUN echo "All verifications passed."
