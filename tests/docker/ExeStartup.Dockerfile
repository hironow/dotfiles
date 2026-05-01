# Lightweight Ubuntu 24.04 image used to e2e-verify
# tofu/exe/coder.tf's startup_script HEREDOC. Mirrors the production
# image family (Ubuntu noble) so package layouts match.
#
# Tools installed:
#   - bash, curl, jq, ca-certificates, gnupg : startup-script's own deps
#   - shellcheck                              : static lint of the script
#   - systemd                                 : systemd-analyze verify on
#                                               the unit files the script
#                                               writes to /etc/systemd/system

ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        gnupg \
        jq \
        shellcheck \
        systemd \
        tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
