# check=skip=InvalidDefaultArgInFrom
#
# The Phase 4 spike's task image: AX's runner contract and nothing else.
#
# AX starts every task container as /usr/local/bin/ax-task-runner, whatever the
# image's entrypoint says (docs/runner.md at the pinned AX: "Your image must
# contain an executable at /usr/local/bin/ax-task-runner"). ko always puts a
# binary at /ko-app/<name>, and a ko-built runner fails its first resume with
# "failed to load /usr/local/bin/ax-task-runner: no such file or directory",
# which is why this is a Dockerfile.
#
# The base is the one exe/ax/.ko.yaml names for the runner (alpine/git: git for
# workspaces, a shell for `ax ssh`), handed in by `just exe-spike-task-image`
# by digest, so the pin lives in one place. No default, on purpose (hence the
# check skipped above): an empty BASE_IMAGE fails the build instead of quietly
# pulling something unpinned.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY ax-task-runner /usr/local/bin/ax-task-runner
ENTRYPOINT ["/usr/local/bin/ax-task-runner"]
