{ pkgs, isDarwin, lib, ... }:

{
  home.packages = with pkgs; [
    # === Core ===
    bash
    coreutils
    curlFull # brew: curl (with extra protocols)
    git
    git-filter-repo
    git-lfs
    gnugrep # brew: grep
    tree
    watch
    wget
    zsh

    # === Search / Navigation ===
    bat
    fd
    fzf
    ripgrep
    ripgrep-all

    # === Shell ===
    sheldon
    starship
    tmux

    # === Dev Tools ===
    just
    jq
    gojq
    yq
    gh
    ghq
    tig
    tokei
    scc
    colordiff
    dprint
    doxygen
    graphviz
    highlight
    pandoc
    universal-ctags

    # === Git Extensions ===
    gibo

    # === Build Tools ===
    cmake
    ninja
    protobuf
    swig

    # === Languages / Runtimes ===
    ruby
    gradle
    maven
    openjdk
    # mono — not commonly in nixpkgs for all platforms

    # === Language Tools ===
    ruff
    semgrep
    sqlc
    shellcheck

    # === Infrastructure / Cloud ===
    opentofu
    tfsec
    kubectl
    kubectx
    helm
    kind
    minikube
    skaffold
    doctl
    flyctl
    azure-cli
    podman

    # === Kubernetes Tools ===
    k9s

    # === Database ===
    sqlite
    goose

    # === Network / HTTP ===
    httpie
    grpcurl
    websocat
    inetutils # brew: telnet
    aria2
    cloudflared
    dnsx
    subfinder
    nuclei
    doggo
    vegeta

    # === DNS / TLS ===
    dnscontrol
    mkcert
    certbot
    unbound

    # === Security / Encryption ===
    age
    sops
    gnupg

    # === Media ===
    ffmpeg
    imagemagick
    ghostscript
    yt-dlp
    espeak-ng
    portaudio
    mecab

    # === Monitoring / System ===
    htop
    ncdu
    gotop

    # === Data / Visualization ===
    # grafana — pulls chromium, fails in Docker sandbox; keep in Brewfile

    # === Libraries (commonly needed as build deps) ===
    openssl
    libgit2
    boost
    glib
    gnutls
    harfbuzz
    pango
    poppler
    libass
    libssh
    libvpx
    nghttp2
    nss
    libopus # brew: opus
    pkg-config # brew: pkgconf
    libpq

    # === Misc CLI ===
    lcov
    pdsh
    pwgen
    yamllint
    mercurial
    vhs
    act
    chezmoi
    ttyd
    mediainfo # brew: media-info

    # === Testing / Performance ===
    k6

    # === Tap packages confirmed in nixpkgs ===
    buf
    # oasdiff — not in nixpkgs, keep in Brewfile
    # teip — not in nixpkgs, keep in Brewfile

    # =====================================================
    # Packages NOT yet migrated (remain in dump/Brewfile):
    # =====================================================
    # Uncertain nixpkgs name / not available:
    #   git-ignore, git-xet, cocoapods, openapi-generator-cli,
    #   swiftformat, swiftlint, terramate, envchain, pinentry_mac,
    #   tcl-tk, srt, tbls, ta-lib, h3, valkey, locust,
    #   fastly-cli, stripe-cli, supabase-cli, dotenvx,
    #   aliyun-cli, flow-cli, kubo, llama-cpp, livekit, livekit-cli,
    #   prek, pushpin, restish, folly, concurrencykit, certifi,
    #   gmt, chawan, fastlane, mecab-ipadic, tesseract,
    #   sphinx-doc, blueutil, ideviceinstaller, ios-deploy,
    #   libusbmuxd, mono, golang-migrate, postgresql_17, llvm,
    #   clang-tools, libomp
    #
    # Tap-specific (no nixpkgs equivalent):
    #   k1low/tap: gh-do, mo, runn
    #   steipete/tap: gogcli, mcporter
    #   schpet/tap: linear
    #   rs/tap: jaggr, jplot
    #   kentaro-m/md2confl: md2confl
    #   kyoshidajp/ghkw: ghkw
    #   grafana/grafana: mcp-k6
    #   akka/brew: akka
    #   crowdin/crowdin: crowdin@4
    #   deploifai/deploifai: deploifai
    #   porter-dev/porter: porter
    #   cameroncooke/axe: axe
    #   ory/tap: cli (ory)
    #   danielgtaylor: restish
  ] ++ lib.optionals isDarwin [
    # macOS-only packages
    mas
    pinentry_mac
  ];
}
