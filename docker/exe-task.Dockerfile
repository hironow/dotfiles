# The exe task image: upstream ax's Dockerfile.task-runner contract (v0.3.1)
# plus the agent CLIs, linux/amd64, built by Cloud Build in the private project
# (exe/ax/cloudbuild.yaml, `just exe-image`).
#
# Contract kept from upstream: the runner at /usr/local/bin/ax-task-runner (ax
# starts every task container as exactly that path), python with the
# google-antigravity package and antigravity_bootstrap.py for its workspace
# bootstrap, and git / curl / ssh / ps / bash. Added: node (for tooling that
# needs it) and the Claude Code binary.
#
# Every input is pinned (tests/unit/test_exe_task_image.py): base images by
# digest, Debian packages through the same dated snapshot the base image was
# built from, python packages by version, the Claude binary by version and
# sha256. The runner and its bootstrap script come from the pinned ax checkout,
# staged into the build context by `just exe-image`.

# The Node.js runtime only; copied, not installed, so no package manager runs.
FROM node:24-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe AS node

FROM python:3.12-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# The snapshot the base image itself names in /etc/apt/sources.list.d.
ARG DEBIAN_SNAPSHOT=20260918T000000Z
RUN printf '%s\n' \
      'Types: deb' \
      "URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" \
      'Suites: trixie trixie-updates' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' \
      '' \
      'Types: deb' \
      "URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}" \
      'Suites: trixie-security' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' \
      > /etc/apt/sources.list.d/debian.sources \
 && echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git libstdc++6 openssh-client procps \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir google-antigravity==0.1.19

COPY --from=node /usr/local/bin/node /usr/local/bin/node

# The native Claude Code binary for this exact version, checked against the
# sha256 in its release manifest
# (https://downloads.claude.ai/claude-code-releases/<version>/manifest.json,
# platforms["linux-x64"].checksum).
ARG CLAUDE_CODE_VERSION=2.1.281
ARG CLAUDE_CODE_SHA256=56fe3da88458465fb27d7e9299dddb3fead55750fb9c2de795f233b5eea6dce1
RUN curl -fsSL -o /usr/local/bin/claude \
      "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}/linux-x64/claude" \
 && echo "${CLAUDE_CODE_SHA256}  /usr/local/bin/claude" | sha256sum -c - \
 && chmod 0755 /usr/local/bin/claude

COPY ax-task-runner /usr/local/bin/ax-task-runner
COPY antigravity_bootstrap.py /usr/local/bin/antigravity_bootstrap.py

ENTRYPOINT ["/usr/local/bin/ax-task-runner"]
