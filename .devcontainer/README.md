# Podman devcontainer

The IDE and host CLI use this directory's single JSON graph: Microsoft's
`base:trixie`, Microsoft/local features, and native Podman 5 or newer. Both the
client and the selected server must meet that minimum. Compose always uses
`PODMAN_COMPOSE_PROVIDER=podman-compose` (the pinned mise tool).

## Launch

Activate the intended engine separately. These commands do not initialize,
start, update, or select a machine. Export the **selected engine-side** Unix
socket before launching the IDE or CLI, from the same process environment.

POSIX (with the canonical tools already installed):

```sh
export PODMAN_COMPOSE_PROVIDER=podman-compose
export DOTFILES_PODMAN_ENGINE_SOCKET="$(podman info --format json | uv run --frozen python -c 'import json,sys; print(json.load(sys.stdin)["host"]["remoteSocket"]["path"].removeprefix("unix://"))')"
bash .devcontainer/require-podman-socket.sh
devcontainer build --workspace-folder . --docker-path podman --docker-compose-path podman-compose --buildkit never
devcontainer up --workspace-folder . --docker-path podman --docker-compose-path podman-compose --buildkit never
devcontainer exec --workspace-folder . --docker-path podman --docker-compose-path podman-compose podman version
```

PowerShell:

```powershell
$env:PODMAN_COMPOSE_PROVIDER = 'podman-compose'
$info = podman info --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Selected Podman engine unavailable' }
$env:DOTFILES_PODMAN_ENGINE_SOCKET = $info.host.remoteSocket.path -replace '^unix://', ''
if ($env:DOTFILES_PODMAN_ENGINE_SOCKET -notmatch '^/run/(.*/)?podman/podman.sock$') { throw 'Selected engine-side Unix socket required' }
devcontainer up --workspace-folder . --docker-path podman --docker-compose-path podman-compose --buildkit never
```

For IDE launch, the operator must configure the **host application User setting** before **Reopen in Container**:

```json
{
  "dev.containers.dockerPath": "podman"
}
```

This setting is application-scoped on the host.
Container customizations cannot select the host engine for initial creation.
Without this prerequisite, the extension still defaults to Docker; do not reopen the container with that default.
The repository does not enforce or verify the operator's host setting, and IDE runtime acceptance remains unverified.
No host settings are written automatically.
The CLI commands above select Podman explicitly.

The public initializer requires canonical `jq`, checks the native client's
`--version` and the selected `info` server version (both >=5), and compares the
reported raw socket (normalizing only `unix://`) exactly with the exported
value. Missing, malformed, old or mismatched metadata fails before startup.
It neither installs tools nor checks a VM socket against the host filesystem.
The source path is
resolved **inside the engine**: never substitute a macOS `/var/folders/...`
host-forwarded API socket or a Windows named pipe for this mount. Those are
separate SDK transport namespaces. No global `DOCKER_HOST` change is needed.
The inside CLI uses `CONTAINER_HOST=unix:///run/dotfiles-podman/podman.sock`.

This mount grants authority over the selected engine, as any outside-engine
socket does. `securityOpt: ["label=disable"]` is scoped to this one container
for SELinux socket access; the host socket is never relabelled or chmodded.
It does not disable host SELinux or add privileged/seccomp/AppArmor overrides.

## Required acceptance versus saved-image checks

`tests/test_just_sandbox.py` builds a unique current tag from a tracked-files-only
snapshot, records its immutable image ID, performs real `devcontainer up` and
`exec`, then checks the same engine inventory and a nested labelled container
roundtrip. Missing prerequisites or build/runtime errors fail, not skip. There
is no `latest` fallback. Saved-image tool, offline and scoped-trust tests in
`tests/test_devcontainer.py` are separate and do not claim lifecycle coverage.

Snapshots never contain the operator's `.git` or untracked files. All tracked
names and their ancestors are validated before any bytes are copied: file and
directory symlinks/junctions, reserved/traversing names and nonregular
substitutions are refused (including dangling links). Ordinary tracked working
changes and staged-only files keep their working-tree bytes; absent files and
gitlinks are omitted. Reads use anchored no-follow descriptors where available;
the Windows branch revalidates metadata before reading. This is not a guarantee
against malicious concurrent filesystem replacement; use a single writer.
Partial snapshots are removed if copying fails before a builder is invoked.
After preparation, a creator removes its captured snapshot only after cleanup
returns with completed accounting successfully persisted. Unknown build or
resource-operation completion, failed resource/engine checks, or a journal
write failure retain that context. Sync-agents uses the same hardened tracked
copy routine; its shared per-test snapshot survives until every one-shot run
has acknowledged durable cleanup.
Host lifecycle snapshots live in owned sibling directories outside the real Git
ancestry, which is checked before build; `up` and `exec` also disable automatic
Git-root/worktree-common-dir mounts. Run lifecycle acceptance from the host.
Nested lifecycle builds are refused: a mapping of the workspace alone cannot
authorize a sibling snapshot outside its Git ancestry.

Existing nested one-shot sandbox binds still require both
`DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1` and an explicit
`LOCAL_WORKSPACE_FOLDER` engine-side path. Container-local sources are never
passed to the outer engine. Real-checkout binds without the disposable fence
are refused.

Cleanup discovers only this run's exact ownership-labelled containers and
also reinspects every recorded immutable ID, even if its label has disappeared.
Actual NotFound is idempotent; changed labels/image/identity or failed queries
retain resources and leave the journal incomplete. The entire version-4 atomic
journal is validated before engine access. It records prepared identities,
build progress (not-started/running/succeeded/interrupted), separate `up`,
controlled `exec`, and one-shot `create` states
(not-started/pending/unknown/completed), the snapshot's **diagnostic-only**
path, and observed IDs. Intent is persisted before each resource-creating call.
`up` completes only after its full immutable CID and inspected run label/image
are persisted; controlled `exec` requires a successful checked roundtrip and
its exact run-specific completion marker. Any nonzero/exceptional call or
missing/invalid receipt remains unknown, regardless of empty discovery or an
owned image nonce. Older journals, including version-3 records without these
operation receipts, are rejected without migration or terminal-state adoption.
CI's always-step refuses malformed journals or a changed selected engine.

`DOTFILES_DEVCONTAINER_MANIFEST` still selects a shared journal when provided.
Otherwise every run durably records its own unique
`.pi/tasks/devcontainer-<run-id>.json` inside this repository (ignored by Git,
not the agent home). The recovery path is printed to stderr. Retain the journal
and reported snapshot for investigation when cleanup is incomplete. Recovery
never deletes a path read from journal metadata, even after successful retries;
only the creating process can remove its own snapshot after persisted cleanup.
This is a serial, single-creator harness. Manual recovery is supported only
after the creator has stopped; concurrent external recovery is unsupported.

The disposable JSON adds `DOTFILES_SANDBOX_RUN_ID` to `containerEnv`, without
changing the image/feature graph. A lost image ID can be recovered only from
the exact preflight-absent run tag, a full immutable ID, and a matching nonce
in its serialized `devcontainer.metadata`. **Actual propagation of that nonce
to an image is not yet verified**; required live acceptance must prove it.
Missing/foreign/ambiguous metadata is retained, never automatically adopted.
A known never-started run still checks tag absence. **Every nonzero build
client result** (including ordinary exit codes 1/125), exception, or signal is
completion-unknown, not a terminal failed build. Original return code/output
and exceptions remain in the chained failure diagnostics if journaling or
cleanup also fails. An unknown/interrupted build stays **incomplete and
retained even if its owned nonce/tag is found or the tag is absent**:
absence at one instant cannot prove a builder has stopped. This requires a
review checkpoint for terminal accounting, not automatic adoption on retry.
The existing `--cleanup-manifest PATH` interface remains available for retries.

All three one-shot consumers (saved-image checks, sandbox commands, and
sync-agents) use checked `podman create`, inspect and persist the full owned
CID, then `podman start --attach CID`. A normally returning empty context is
not creation evidence. After positively recorded creation, attached-start
application exit codes remain unchanged, including intentional failures;
cleanup must acknowledge exact-ID removal or actual NotFound, not merely a
matching identity. Creation uncertainty never becomes complete through an
empty label lookup. Known completed operations are not reclassified as unknown
because an unrelated test assertion fails.

For accounted terminal builds it removes only the fresh random image **tag**,
using two-argument `podman untag IMAGE_ID TAG` after fresh selected-engine and
tag-ID checks. Image IDs/build caches, foreign aliases and new references are
retained. No FROM wrapper, image prune or image-ID deletion runs. Untrappable
termination can leave labelled resources; it never authorizes broader cleanup.

Both engine CI jobs call `ci-bootstrap.sh`, which refuses non-hosted/non-Linux
or root execution. It uses the scoped native installer, canonical generated
mise tool declarations, pinned/checksummed mise bootstrap, and this same
non-root user's socket. Only ephemeral CI starts that service and removes the
Docker executable from its PATH. The paused sandbox variable remains paused.
