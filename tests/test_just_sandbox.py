import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
IMAGE = "dotfiles-just-sandbox:latest"

# CI sets this (the `env:` block of .github/workflows/test-just.yaml) to state
# that the checkout at LOCAL_WORKSPACE_FOLDER is a runner checkout thrown away
# with the job, and may therefore be bind-mounted and written to.
DISPOSABLE_CHECKOUT_ENV = "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT"


def _mount_mode(env: Mapping[str, str]) -> Literal["bind", "snapshot"]:
    """Decide what `run_in_sandbox` may mount at /root/dotfiles.

    Every sandbox script is prefixed with `_GIT_INIT`, which runs `git init`,
    OVERWRITES `.git/info/exclude` and `git add -A` in the mounted tree, and
    recipes like `just fmt` write to it as well. That is only ever safe on a
    disposable copy.

    LOCAL_WORKSPACE_FOLDER is NOT that proof: devcontainer.json exports it
    inside the dev container too, so `just test` from a dev container on a
    developer machine would point it at the real working repo. Only CI knows
    its checkout is disposable, so CI has to say so explicitly.

    The remaining case -- LOCAL_WORKSPACE_FOLDER set, nothing declaring it
    disposable -- is refused rather than silently snapshotted: a snapshot made
    inside the dev container is a CONTAINER path that the outer daemon cannot
    resolve, so `-v` would mount an empty dir and the whole suite would fail
    obscurely. Fail loudly with the reason instead.
    """
    local_workspace = env.get("LOCAL_WORKSPACE_FOLDER")
    if local_workspace is None:
        return "snapshot"
    if env.get(DISPOSABLE_CHECKOUT_ENV) == "1":
        return "bind"
    raise RuntimeError(
        f"refusing to bind-mount {local_workspace!r} into the sandbox: it looks "
        "like a real working checkout, and the sandbox runs `git init`, "
        "overwrites .git/info/exclude and `git add -A` in whatever it mounts. "
        f"Only CI may bind a checkout, by setting {DISPOSABLE_CHECKOUT_ENV}=1. "
        "Run `just test` from the host, not from inside the dev container."
    )


def _host_workspace_path() -> str:
    """Resolve the path that the outer docker daemon will mount.

    When tests run inside the dev container under docker-outside-of-
    docker, `-v <src>:<dst>` is interpreted by the host daemon, so
    <src> must be a HOST path. devcontainer.json exports the host
    path as LOCAL_WORKSPACE_FOLDER for exactly this case.

    When tests run on the host directly (no dev container), ROOT
    already is a host path.
    """
    return os.environ.get("LOCAL_WORKSPACE_FOLDER", str(ROOT))


def _run(
    cmd: list[str] | str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        shell=isinstance(cmd, str),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _docker_available() -> bool:
    r = _run(["docker", "info"])
    return r.returncode == 0


def _devcontainer_cli_available() -> bool:
    r = _run(["devcontainer", "--version"])
    return r.returncode == 0


@pytest.fixture(scope="session")
def docker_image():
    # given: docker daemon and devcontainer.json availability
    if not _docker_available():
        pytest.skip("Docker is not available on host; skipping sandbox tests.")

    if not DEVCONTAINER_JSON.exists():
        pytest.skip("devcontainer.json missing; skipping.")

    # In CI, the dev container image is prebuilt by the
    # `devcontainers/ci` action with imageName=dotfiles-just-sandbox.
    # We reuse it instead of rebuilding so that a build failure surfaces
    # as a CI step error (not as a silent pytest.skip that lets the
    # workflow report green).
    if _image_exists(IMAGE):
        yield IMAGE
        return

    # Local fallback: build the dev container image via the devcontainer
    # CLI. Requires `npm i -g @devcontainers/cli` on the host.
    if not _devcontainer_cli_available():
        pytest.skip(
            "Image 'dotfiles-just-sandbox:latest' not present and the "
            "@devcontainers/cli is not installed on the host. Either "
            "  npm i -g @devcontainers/cli\n"
            "or pull the prebuilt CI image (when ghcr publish is enabled). "
            "CI uses devcontainers/ci action, so this branch is only for "
            "local pytest invocations."
        )

    build_cmd = [
        "devcontainer",
        "build",
        "--workspace-folder",
        str(ROOT),
        "--image-name",
        IMAGE,
    ]
    result = _run(build_cmd, cwd=ROOT)
    if result.returncode != 0:
        pytest.fail(
            "Failed to build dev container image via devcontainer CLI.\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )

    # then: image is available
    yield IMAGE


def _image_exists(image: str) -> bool:
    r = _run(["docker", "image", "inspect", image])
    return r.returncode == 0


def _snapshot_tracked_worktree(src: str) -> str:
    """Copy only git-tracked files into a throwaway host tempdir.

    The sandbox container must never see the real repo: its 3.6G `.git`
    (history + credentials), untracked secrets (`private/`), and caches must
    stay out, and any file a test writes (fmt, dump truncation, symlinks) must
    land on a disposable copy — not the host working tree via a bind mount.
    `git ls-files` yields exactly the first-party tracked set (submodule
    gitlinks, `.git`, `.venv`, `node_modules`, caches are all excluded), so we
    copy just those (~hundreds of files) with the stdlib (no rsync/tar dep).
    """
    snapshot = tempfile.mkdtemp(prefix="dotfiles-sandbox-")
    tracked = subprocess.run(
        ["git", "-C", src, "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode()
    for rel in tracked.split("\0"):
        if not rel:
            continue
        source = Path(src) / rel
        if not source.is_file():  # skip gitlinks / vanished paths
            continue
        dest = Path(snapshot) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest, follow_symlinks=False)
    return snapshot


def run_in_sandbox(image: str, script: str) -> subprocess.CompletedProcess:
    # The dev container image does NOT bake /root/dotfiles into its layers —
    # that path is the workspace mount. A fresh `docker run` starts empty, so we
    # recreate it. Under docker-outside-of-docker (CI) the mount source must be
    # a host path and the checkout is ephemeral, so we bind-mount it directly.
    # Locally we snapshot only git-tracked files into a host tempdir and mount
    # THAT, so the real repo (and its .git) never enters the throwaway container
    # and tests can never pollute the host. `_mount_mode` holds that fence.
    full_script = textwrap.dedent(
        f"""
        set -e
        cd /root/dotfiles
        {script}
        """
    ).strip()
    src = _host_workspace_path()
    snapshot_dir = None
    if _mount_mode(os.environ) == "bind":
        mount_source = src
    else:
        snapshot_dir = _snapshot_tracked_worktree(src)
        mount_source = snapshot_dir
    docker_args = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{mount_source}:/root/dotfiles",
        "-w",
        "/root/dotfiles",
        # devcontainers/ci action bakes the dev container's
        # containerEnv (including MISE_OFFLINE=1) into the saved
        # image as ENV layer. Inner test containers want a fresh
        # mise cache resolution, so override.
        "-e",
        "MISE_OFFLINE=0",
    ]
    # Forward GITHUB_TOKEN so mise's `latest` resolution against
    # api.github.com hits the authenticated 5000/hr quota. CI
    # surfaces it via the workflow's `env:` block; locally it is
    # only set if the operator already has GH_TOKEN/GITHUB_TOKEN
    # exported.
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if gh_token:
        docker_args.extend(["-e", f"GITHUB_TOKEN={gh_token}"])
    docker_args.extend([image, "bash", "-lc", full_script])
    try:
        return _run(docker_args)
    finally:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def _sh_single_quote(s: str) -> str:
    """Quote a string for single-quoted shell embedding.

    Replaces ' with the safe sequence '"'"'.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


# Build git stub scripts using textwrap for clarity
GIT_STUB_SIMPLE = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

GIT_STUB_RERUN = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "pull" ] || [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

SCRIPT_INSTALL_SUCCESS = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: pass-through except clone of zgen/dotfiles and ignore; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_SIMPLE)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    # gcloud is now installed via the google-cloud-cli devcontainer
    # feature, so install.sh's `command -v gcloud` returns true and
    # the install path no-ops naturally. No INSTALL_SKIP_GCLOUD needed.
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_ADD_UPDATE=1;
    # run install and verify link
    bash ./install.sh && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()

SCRIPT_INSTALL_RERUN = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: only 'pull' is no-op in rerun path; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_RERUN)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    # gcloud is now installed via the google-cloud-cli devcontainer
    # feature, so install.sh's `command -v gcloud` returns true and
    # the install path no-ops naturally. No INSTALL_SKIP_GCLOUD needed.
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_ADD_UPDATE=1;
    # first run (clone branch)
    bash ./install.sh;
    # Initialise a real git repo at DOTPATH to exercise stash/checkout.
    # The DOTPATH dir was `cp -a`'d from /root/dotfiles which already
    # contains a populated .git/ (the bind-mounted host repo). Wipe it
    # first so `git init` produces a fresh empty repo and the
    # subsequent commit has actual content to record.
    cd "$DOTPATH";
    rm -rf .git;
    git init;
    git add -A;
    git -c user.name=test -c user.email=test@example.com commit -m initial --allow-empty;
    git branch -M main;
    cd - >/dev/null;
    # second run (update branch)
    bash ./install.sh;
    # verify link remains correct
    test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()


# A `mise` wrapper that records every invocation and no-ops the
# `install` subcommand. `just deploy` now provisions the host-global
# toolchain via `mise -C / install` (cwd=/ so only the global config
# resolves; see justfile). Without this stub the deploy sandbox tests
# would try to install the entire global config (rust/java/AI CLIs/...)
# inside the throwaway container. The wrapper logs argv to
# /tmp/mise-calls.log so a test can assert the HOME-independent
# `-C / install` wiring, and delegates every non-install call
# (e.g. `mise x -- sheldon lock`) to the real mise at /usr/bin/mise.
_MISE_RECORD_STUB = (
    "mkdir -p /tmp/stubs && "
    "printf '%s\\n' "
    "'#!/bin/sh' "
    "'echo \"$@\" >> /tmp/mise-calls.log' "
    '\'for a in "$@"; do [ "$a" = install ] && exit 0; done\' '
    "'exec /usr/bin/mise \"$@\"' "
    "> /tmp/stubs/mise && chmod +x /tmp/stubs/mise && "
    "export PATH=/tmp/stubs:$PATH && "
)


def _case_id(params):
    # Prefer the explicit human-friendly name (first param)
    if isinstance(params, (list, tuple)) and params:
        return str(params[0])
    values = getattr(params, "values", None)
    if isinstance(values, (list, tuple)) and values:
        return str(values[0])
    return None


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "help_lists_targets",
            "just help",
            0,
            "install",
            "",
            id="Help: lists targets",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "validate_path_duplicates",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export PATH=/tmp/x1:/tmp/x2:$PATH && just validate-path-duplicates",
            2,
            "command: foo",
            "",
            id="Validate: duplicates found",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_no_duplicates",
            "mkdir -p /tmp/only && printf '#!/bin/sh\necho ok\n' > /tmp/only/foo && chmod +x /tmp/only/foo && VALIDATE_PATH=/tmp/only just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
            id="Validate: no duplicates",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_path_structural_roots",
            'H=$(mktemp -d) && mkdir -p "$H/.grok/bin" "$H/.local/bin" && '
            ': > "$H/.grok/bin/foo" && chmod +x "$H/.grok/bin/foo" && '
            'cp "$H/.grok/bin/foo" "$H/.local/bin/foo" && '
            'HOME="$H" VALIDATE_PATH="$H/.grok/bin:$H/.local/bin" '
            "just validate-path-duplicates",
            0,
            "structural duplicate(s) ignored",
            "",
            id="Validate: managed roots (.grok/.local/bin) ignored",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_path_spaces",
            "mkdir -p /tmp/sa /tmp/sb && : > /tmp/sa/prog && "
            "chmod +x /tmp/sa/prog && "
            ': > "/tmp/sb/prog (variant)" && chmod +x "/tmp/sb/prog (variant)" && '
            "VALIDATE_PATH=/tmp/sa:/tmp/sb just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
            id="Validate: space-in-name not a false duplicate",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "deploy_and_clean_link",
            # `_MISE_RECORD_STUB` no-ops `just deploy`'s `mise -C / install`
            # so this case stays a fast symlink check (see stub comment).
            _MISE_RECORD_STUB
            + "rm -f ~/.zshrc && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: basic",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "deploy_idempotent",
            _MISE_RECORD_STUB
            + "rm -f ~/.zshrc && just deploy && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: idempotent",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "install_sh_success",
            SCRIPT_INSTALL_SUCCESS,
            0,
            "",
            "",
            id="Install: first run",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "install_sh_rerun",
            SCRIPT_INSTALL_RERUN,
            0,
            "",
            "",
            id="Install: rerun update path",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "check_path_runs",
            "just check-path",
            0,
            "\n",
            "",
            id="Check: path prints",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "nvcc_version_ok",
            "just check-version-nvcc 12.3",
            0,
            "",
            "",
            id="Versions: NVCC ok",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "nvcc_version_mismatch",
            "just check-version-nvcc 11.4",
            1,
            "",
            "Expected NVCC version 11.4",
            id="Versions: NVCC mismatch",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "torch_not_installed",
            "just check-version-torch 2.5.1",
            1,
            "",
            "PyTorch is not installed",
            id="Versions: Torch missing",
            marks=pytest.mark.versions,
        ),
    ],
)
def test_just_commands_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    # given: sandbox image with repository and stubs
    # when: run the just command inside container
    result = run_in_sandbox(docker_image, script)

    # then: verify exit code and expected output markers
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    if expect_out:
        assert expect_out in result.stdout, (
            f"{name}: expected stdout to contain: {expect_out!r}\nstdout:\n{result.stdout}"
        )


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "doctor_path_duplicates_warn",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export VALIDATE_PATH=/tmp/x1:/tmp/x2 && just doctor",
            0,
            "duplicate command names found",
            "",
            id="Doctor: PATH duplicates warn",
            marks=pytest.mark.validate,
        ),
    ],
)
def test_additional_scenarios_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_reports_just(docker_image):
    # when
    result = run_in_sandbox(docker_image, "just doctor")
    # then
    assert result.returncode == 0, (
        f"doctor failed: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK   just" in result.stdout


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out",
    [
        pytest.param(
            "Check: my IP ok",
            "just check-myip",
            0,
            "",
            id="Check: my IP ok",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: docker ports guarded",
            # docker-cli is installed in the dev container image (by the
            # docker-outside-of-docker feature), but no dockerd runs inside
            # the sandbox. Guard on actual daemon reachability so the
            # CLI-without-daemon case is treated as 'no docker available'
            # — which it effectively is for any operation that matters.
            "if command -v docker >/dev/null 2>&1 && "
            "docker info >/dev/null 2>&1; "
            "then just check-dockerport; else echo skip-docker; fi",
            0,
            "skip-docker",
            id="Check: docker ports guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: brew guarded",
            "if command -v brew >/dev/null 2>&1; then just check-brew; else echo skip-brew; fi",
            0,
            "skip-brew",
            id="Check: brew guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            # gcloud is installed at devcontainer build time via the
            # local `dotfiles-tools` feature, so the guard's true
            # branch fires and the recipe runs end-to-end. Just
            # assert it succeeds (no specific stdout).
            "Check: gcloud guarded",
            "if command -v gcloud >/dev/null 2>&1; then just check-gcloud; else echo skip-gcloud; fi",
            0,
            "",
            id="Check: gcloud guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: npm globals available",
            # npm is shipped in the sandbox image (needed by mise's npm-backed
            # tools), so the guard always falls through to the real recipe.
            # `npm ls --global --depth 0` exits 0 even with no globals.
            "just check-npm-g",
            0,
            "",
            id="Check: npm globals available",
            marks=pytest.mark.check,
        ),
        pytest.param(
            # check-pnpm-dlx is a record-only listing (grep over dump/npm-dlx).
            # pnpm itself is not required; the recipe always exits 0 and
            # prints the header line.
            "Check: pnpm dlx record listed",
            "just check-pnpm-dlx",
            0,
            "pnpm dlx packages",
            id="Check: pnpm dlx record listed",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: rust cfg guarded",
            "if command -v rustc >/dev/null 2>&1; then just check-rust; else echo skip-rust; fi",
            0,
            "skip-rust",
            id="Check: rust cfg guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: watchman guarded",
            "if command -v watchman >/dev/null 2>&1; then just check-watchman; else echo skip-watchman; fi",
            0,
            "skip-watchman",
            id="Check: watchman guarded",
            marks=pytest.mark.check,
        ),
    ],
)
def test_check_commands_sandbox(docker_image, name, script, expect_rc, expect_out):
    # given / when
    result = run_in_sandbox(docker_image, script)
    # then
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_sandbox(docker_image):
    result = run_in_sandbox(docker_image, "just doctor")
    assert result.returncode == 0, (
        f"doctor failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Doctor summary:" in result.stdout


# The add-* recipes all share the same early guard:
#   if the dump file is missing or empty, exit 1 with "missing or empty".
# These tests cover that guard without needing gcloud/brew/pnpm in the
# sandbox: the guard fires before any tool is invoked.
@pytest.mark.parametrize(
    "recipe, filename",
    [
        pytest.param("add-brew", "Brewfile", id="add-brew guards empty Brewfile"),
        pytest.param("add-gcloud", "gcloud", id="add-gcloud guards empty dump"),
    ],
)
@pytest.mark.check
def test_add_recipes_guard_empty_dump(docker_image, recipe, filename):
    # given: a synthetic host dir 'testhost' holding an empty manifest. We only
    # ADD dump/testhost/ (never truncate the tracked dump/<host>/ manifests) so
    # CI's bind-mounted checkout is never corrupted for later tests (ADR 0030),
    # and we remove it again afterwards for the same reason — CI mounts one
    # checkout for the whole job, so what a test adds, a test must take away.
    # when: the recipe restores from that host (DOTFILES_HOST=testhost)
    # then: it exits 1 with a clear "missing or empty" message
    script = (
        f"mkdir -p dump/testhost && : > dump/testhost/{filename} ; "
        f"rc=0 && DOTFILES_HOST=testhost just {recipe} || rc=$? ; "
        # rmdir, not a recursive delete: it must fail loudly rather than erase
        # anything the recipe was not supposed to leave in there.
        f"rm -f dump/testhost/{filename} ; rmdir dump/testhost ; "
        "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 1, (
        f"{recipe}: expected rc=1 for empty dump/testhost/{filename}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "missing or empty" in result.stdout, (
        f"{recipe}: expected 'missing or empty' in stdout\nstdout:\n{result.stdout}"
    )


# Per-host dump host-alias resolution (ADR 0030). These exercise the recipe
# wiring and scripts/dump_host.sh. All `.host`-writing / layout-mutating cases
# run against an isolated DOTFILES_DUMP_DIR tempdir so they never touch the real
# tracked dump/ or the real dump/.host — keeping CI's bind-mounted checkout
# clean and the tests order-independent.
@pytest.mark.check
def test_dump_fails_without_host_alias(docker_image):
    """`just dump` must fail loud when no host alias is resolvable (no
    DOTFILES_HOST, no dump/.host) BEFORE touching brew/gcloud: you declare
    which host you are before recording it (ADR 0030)."""
    # Point the resolver at an empty tempdir: no .host, no host dirs.
    script = 'DOTFILES_HOST= DOTFILES_DUMP_DIR="$(mktemp -d)" just dump'
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0, (
        f"dump should fail-loud without a host alias\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "host alias" in (result.stdout + result.stderr)


@pytest.mark.check
def test_set_host_writes_and_validates(docker_image):
    """`just set-host` records a valid alias and rejects an invalid slug
    (ADR 0030). Isolated via DOTFILES_DUMP_DIR so the real dump/.host is
    untouched."""
    ok = run_in_sandbox(
        docker_image,
        'd="$(mktemp -d)"; DOTFILES_DUMP_DIR="$d" just set-host macmini '
        '&& cat "$d/.host"',
    )
    assert ok.returncode == 0, f"set-host valid failed:\n{ok.stdout}\n{ok.stderr}"
    assert "macmini" in ok.stdout

    bad = run_in_sandbox(
        docker_image,
        'DOTFILES_DUMP_DIR="$(mktemp -d)" just set-host "bad host"',
    )
    assert bad.returncode != 0
    assert "invalid" in (bad.stdout + bad.stderr)


@pytest.mark.check
def test_dump_host_helper_resolves_restore(docker_image):
    """scripts/dump_host.sh resolve-restore: a lone host dir auto-resolves,
    multiple require an explicit pick, and an unknown alias is rejected
    (ADR 0030). Fully isolated in a tempdir."""
    script = textwrap.dedent(
        """
        d="$(mktemp -d)"
        mkdir -p "$d/only"
        printf 'single=%s\\n' \
          "$(DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore)"
        mkdir -p "$d/second"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore >/dev/null 2>&1; then
          echo "multi=UNEXPECTED_OK"
        else
          echo "multi=rejected"
        fi
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore nope >/dev/null 2>&1; then
          echo "missing=UNEXPECTED_OK"
        else
          echo "missing=rejected"
        fi
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 0, (
        f"helper probe failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "single=only" in result.stdout
    assert "multi=rejected" in result.stdout
    assert "missing=rejected" in result.stdout


@pytest.mark.check
def test_set_host_rejects_shell_metachars(docker_image):
    """just parameter quoting (ADR 0030): a metacharacter alias must be passed
    as a single quoted arg and rejected by the validator, never executed as a
    shell command. Regression for the {{quote(alias)}} boundary."""
    marker = "/tmp/dump_host_injection_marker"
    script = textwrap.dedent(
        f"""
        d="$(mktemp -d)"
        rm -f {marker}
        if DOTFILES_DUMP_DIR="$d" just set-host 'x"; touch {marker}; #'; then
          echo "outcome=UNEXPECTED_OK"
        else
          echo "outcome=rejected"
        fi
        test -e {marker} && echo "side_effect=INJECTED" || echo "side_effect=none"
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert "outcome=rejected" in result.stdout, result.stdout
    assert "side_effect=none" in result.stdout, result.stdout
    assert "INJECTED" not in result.stdout


@pytest.mark.check
def test_dump_host_rejects_unsafe_host(docker_image):
    """scripts/dump_host.sh hardening (ADR 0030): a multi-line hand-edited
    dump/.host is rejected (not silently truncated to line 1), and a symlinked
    dump/<host> is refused so brew bundle cannot read outside the tree."""
    script = textwrap.dedent(
        """
        d="$(mktemp -d)"
        printf 'macbook\\nmalicious\\n' > "$d/.host"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-dump >/dev/null 2>&1; then
          echo "multiline=UNEXPECTED_OK"
        else
          echo "multiline=rejected"
        fi
        rm -f "$d/.host"
        mkdir -p "$d/real"
        ln -s "$d/real" "$d/linked"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore linked >/dev/null 2>&1; then
          echo "symlink=UNEXPECTED_OK"
        else
          echo "symlink=rejected"
        fi
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert "multiline=rejected" in result.stdout, result.stdout
    assert "symlink=rejected" in result.stdout, result.stdout
    assert "UNEXPECTED_OK" not in result.stdout


# =============================================================================
# Format / Lint Recipe Tests
# =============================================================================
#
# `just fmt` / `just lint` chain `uv run --frozen --only-group lint ruff` (Python), `mise x -- shellcheck`
# (lint only), and `mise x -- prettier` (both). The sandbox image ships mise,
# and shellcheck is listed in mise.toml, so shellcheck runs for real here.
#
# Prettier is intentionally NOT in mise.toml (the team relies on host install
# via brew/asdf), so we override `mise x -- prettier ...` with a no-op shim.
# We do this by injecting a wrapper named `mise` earlier on PATH that:
#   - intercepts the literal pattern `x -- prettier ...` and exits 0,
#   - delegates everything else to the real mise (apt-installed at /usr/bin/mise).

# mise's tools (incl. shellcheck) are pre-installed in the sandbox image
# (Dockerfile runs `mise trust && mise install` at build time). We only need
# to override prettier — which is intentionally NOT in mise.toml — with a
# no-op shim so `just fmt`/`just lint` finish cleanly without prettier.
# Shellcheck runs for real via the pre-installed mise tool.
#
# Each one-shot container starts with an empty mise cache for the
# workspace tools, so `mise x -- shellcheck` (and friends) need the
# network to resolve "latest" against the aqua-registry. We do NOT
# set MISE_OFFLINE=1 here — GitHub Actions runners get an
# authenticated 5000/hr token via the dev container's environment,
# and the post-create.sh's `mise install` already populates the
# cache for the dev container itself. In one-shot inner containers,
# accept the ~5s warm-up.
_MISE_PRETTIER_STUB = (
    "mkdir -p /tmp/stubs && "
    "printf '%s\\n' "
    "'#!/bin/sh' "
    '\'if [ "$1" = x ] && [ "$2" = -- ] && [ "$3" = prettier ]; then exit 0; fi\' '
    "'exec /usr/bin/mise \"$@\"' "
    "> /tmp/stubs/mise && chmod +x /tmp/stubs/mise && "
    "export PATH=/tmp/stubs:$PATH && "
)

# Backwards-compat alias used by older tests; same semantics now.
_MISE_STUB = _MISE_PRETTIER_STUB

# The sandbox image excludes .git via .dockerignore, so `git ls-files` would
# fatal. Initialize a repo and stage everything so `git ls-files` returns the
# tracked file list. Empty `git ls-files` output makes grep exit 1 (no match),
# which would then break the pipeline under `set -e`.
#
# Submodule paths are intentionally NOT staged: in a real checkout, `git
# ls-files` omits files inside submodules (each submodule is a pointer in
# the parent repo). Without this, our throwaway `git init` would include
# every submodule's .sh / file and cause shellcheck/prettier/ruff/... to
# scan third-party code the recipes are designed to skip. We derive the
# exclusion list dynamically from .gitmodules so nested submodules
# (e.g. tools/tmux/plugins/tmux-resurrect) are covered too.
# SAFETY: the git writes below (including the `.git/info/exclude` overwrite) are
# only safe on a disposable tree, so `_mount_mode` guarantees one: locally a
# throwaway snapshot of just the tracked files (no host .git — see
# _snapshot_tracked_worktree), in CI the runner checkout it declares disposable,
# and a refusal in every other case. They can never reach a real repo. We
# init a normal repo at /root/dotfiles/.git, which `prek install` /
# `just install-hooks` need (they wire hooks into .git/hooks).
_GIT_INIT = (
    "cd /root/dotfiles && "
    "git init -q && "
    "git config user.email t@e && git config user.name t && "
    "git config --file .gitmodules --get-regexp path 2>/dev/null "
    "| awk '{print $2\"/\"}' > .git/info/exclude && "
    "git add -A 2>/dev/null && "
)


@pytest.mark.check
def test_just_lint_passes_on_clean_tree(docker_image):
    """`just lint` returns 0 on the as-shipped repo (ruff finds no violations)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just lint")
    assert result.returncode == 0, (
        f"just lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Python (ruff check" in result.stdout
    assert "lint done" in result.stdout


@pytest.mark.check
def test_just_fmt_passes_on_clean_tree(docker_image):
    """`just fmt` returns 0 on the as-shipped repo (ruff format applies cleanly)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just fmt")
    assert result.returncode == 0, (
        f"just fmt failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Python (ruff format)" in result.stdout
    assert "fmt done" in result.stdout


@pytest.mark.check
def test_just_check_passes_on_clean_tree(docker_image):
    """`just check` is the strict gate (no writes). Must pass on as-shipped tree."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just check")
    assert result.returncode == 0, (
        f"just check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "All checks passed" in result.stdout


@pytest.mark.check
def test_just_install_hooks_wires_prek_into_git(docker_image):
    """`just install-hooks` runs `prek install` and writes a git pre-commit hook.

    The hook it writes is removed again: in CI the mounted `.git` is the real
    checkout's, and nothing else in the suite wants a pre-commit hook there.
    Only the one file prek creates is removed, never `.git/hooks` itself.
    """
    script = (
        _GIT_INIT
        + "rc=0 && { just install-hooks && "
        + "[ -f .git/hooks/pre-commit ] && echo 'pre-commit hook present' ; } "
        + "|| rc=$? ; "
        + "rm -f .git/hooks/pre-commit ; "
        + "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 0, (
        f"install-hooks failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "pre-commit hook present" in result.stdout


@pytest.mark.check
def test_just_lint_detects_ruff_violation(docker_image):
    """`just lint` exits non-zero when a Python file has a ruff violation
    that ruff cannot auto-fix.

    Uses F821 (undefined name), which is in ruff's default rule set and has
    no auto-fix — so even with `--fix` the lint step fails.

    The plant is removed again before the script exits; see the note above
    `_planted` below for why that is not optional in CI. Left behind, this one
    file made every later `just check` in the job die at ruff instead of
    reaching the leg it was testing.
    """
    script = (
        _MISE_STUB
        + _GIT_INIT
        + "printf 'def f():\\n    return undefined_name\\n' > bad_lint.py ; "
        + "rc=0 && just lint || rc=$? ; "
        + "rm -f bad_lint.py ; "
        + "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0, (
        "just lint should fail on F821 violation\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "F821" in result.stdout or "F821" in result.stderr


# `just check` passing on a clean tree says the gate runs; it does not say the
# gate would notice anything. These two plant a violation and require a
# non-zero exit, so a leg that is dropped from the recipe fails a test instead
# of quietly widening what we ship. They were written against a justfile with
# the matching leg deleted and they failed there first; with the leg present
# they pass.
#
# One leg each from the two kinds of discovery the recipe uses, because the two
# disagree about untracked files and both behaviours are load-bearing:
# markdownlint is fed from `git ls-files`, so it sees tracked files only, while
# check_storage_bounds.py globs the filesystem and sees a sink that was never
# added.
#
# Both clean up the file they plant, which matters only in CI: there
# run_in_sandbox bind-mounts the (disposable) runner checkout itself
# instead of a per-call snapshot, so a planted violation left behind would
# travel to every later test in the job and fail the clean-tree checks. The
# `|| rc=$?` is what makes that reachable -- the harness runs under `set -e`,
# so a bare `just check` on a failing gate would exit before any cleanup.


def _planted(setup: str, cleanup: str) -> str:
    """Run `just check` with a violation planted, then undo it and re-raise.

    Keeps the gate's own exit status as the script's, so the assertions below
    read the gate and not the cleanup.
    """
    return (
        _MISE_STUB
        + _GIT_INIT
        + setup
        + "rc=0 && just check || rc=$? ; "
        + cleanup
        + "exit $rc"
    )


@pytest.mark.check
def test_just_check_detects_markdownlint_violation(docker_image):
    """`just check` exits non-zero when a TRACKED markdown file breaks a rule.

    MD047 (single trailing newline) is in markdownlint's default set and
    `.markdownlint.json` does not switch it off, so a file with no final
    newline violates exactly that one rule and nothing else.

    The `git add` is load-bearing, not tidiness: the recipe pipes
    `git ls-files '*.md'` into markdownlint, so an untracked .md is invisible
    to this leg. `docs/` is used because `.markdownlint-cli2.yaml` ignores the
    `ROOT_AGENTS_*.md` instruction sources and `templates/**` by design -- a
    violation planted there would prove nothing.
    """
    script = _planted(
        setup=(
            "printf 'Planted: this file has no trailing newline.' "
            "> docs/planted_md_violation.md && "
            "git add docs/planted_md_violation.md && "
        ),
        cleanup=(
            "git rm -q --cached docs/planted_md_violation.md ; "
            "rm -f docs/planted_md_violation.md ; "
        ),
    )
    result = run_in_sandbox(docker_image, script)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "just check should fail on an MD047 violation in a tracked .md\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "MD047" in combined, f"expected MD047 in the output:\n{combined}"
    # The gate reached this leg rather than dying earlier for some other reason.
    # Do NOT assert on "All checks passed" here: that is ruff's and ty's own
    # per-step output, printed well before the recipe's `✅ All checks passed.`
    # banner, so it appears in a run that failed.
    assert "Markdown (markdownlint-cli2)" in result.stdout, (
        f"the gate never reached the markdownlint leg:\n{result.stdout}"
    )


@pytest.mark.check
def test_just_check_detects_unbounded_storage_sink(docker_image):
    """`just check` exits non-zero when a tofu bucket declares no bound.

    The planted bucket is deliberately correct in every other respect --
    uniform bucket-level access, enforced public-access prevention, zero
    soft-delete retention -- so the single thing it fails is the bound rule
    itself. `tests/unit/test_storage_bounds.py` owns whether that rule is
    right; this test owns whether `just check` actually runs it.

    Nothing is staged here, unlike the markdownlint leg above:
    check_storage_bounds.py globs `tofu/**/*.tf` off the filesystem, so an
    untracked sink is still caught. That asymmetry is the point of having both.
    """
    # Single-quoted for the shell below, so the HCL's double quotes need no
    # escaping; only the newlines are printf escapes.
    bucket = (
        'resource "google_storage_bucket" "planted" {\\n'
        '  name                        = "planted-no-bound"\\n'
        '  location                    = "US"\\n'
        "  uniform_bucket_level_access = true\\n"
        '  public_access_prevention    = "enforced"\\n'
        "  soft_delete_policy {\\n"
        "    retention_duration_seconds = 0\\n"
        "  }\\n"
        "}\\n"
    )
    script = _planted(
        setup=(f"mkdir -p tofu/planted && printf '{bucket}' > tofu/planted/bad.tf && "),
        # rmdir, not a recursive delete: if anything else ever lands in that
        # directory the cleanup should fail loudly rather than erase it.
        cleanup="rm -f tofu/planted/bad.tf ; rmdir tofu/planted ; ",
    )
    result = run_in_sandbox(docker_image, script)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "just check should fail on a google_storage_bucket with no bound\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "check-storage-bounds: FAILED" in combined, (
        f"expected the storage-bounds gate to report a failure:\n{combined}"
    )
    assert "is unbounded" in combined, (
        f"expected the unbounded-sink violation to name the sink:\n{combined}"
    )
    # See the note in the markdownlint test: "All checks passed" is ruff's and
    # ty's own output and says nothing about the recipe's verdict.
    assert "storage bounds" in result.stdout, (
        f"the gate never reached the storage-bounds leg:\n{result.stdout}"
    )


# =============================================================================
# clean-work-env Recipe Tests
# =============================================================================


@pytest.mark.check
def test_just_clean_work_env_rejects_unknown_target(docker_image):
    """`just clean-work-env x` for x not in {a,b,c,d} fails with a clear error."""
    result = run_in_sandbox(docker_image, "just clean-work-env z")
    assert result.returncode != 0
    assert "unknown target" in result.stdout or "unknown target" in result.stderr


@pytest.mark.check
def test_just_clean_work_env_fails_when_dir_missing(docker_image):
    """`just clean-work-env a` fails if ~/.claude-work-a does not exist."""
    result = run_in_sandbox(
        docker_image,
        "rm -rf $HOME/.claude-work-a && just clean-work-env a",
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "does not exist" in combined


@pytest.mark.check
def test_just_clean_work_env_resets_managed_paths_only(docker_image):
    """`just clean-work-env a` empties CLAUDE.md and removes the managed
    directories (skills/commands/agents/plans/session-env/shell-snapshots)
    while preserving plugins/, projects/, and history files.
    """
    setup = (
        "set -eu\n"
        "d=$HOME/.claude-work-a\n"
        "mkdir -p $d/skills/foo $d/commands $d/agents $d/plans $d/session-env "
        "$d/shell-snapshots $d/plugins/keep-me $d/projects/keep-me\n"
        "echo 'KEEP THIS' > $d/CLAUDE.md\n"
        "echo 'foo skill' > $d/skills/foo/SKILL.md\n"
        "echo 'cmd' > $d/commands/c.md\n"
        "echo 'plan' > $d/plans/p.md\n"
        "echo 'plugin file' > $d/plugins/keep-me/p.json\n"
        "echo 'project file' > $d/projects/keep-me/x.json\n"
        "echo 'history' > $d/.claude.json\n"
        "just clean-work-env a\n"
        "# inspect aftermath\n"
        "[ -f $d/CLAUDE.md ] && [ ! -s $d/CLAUDE.md ] && echo 'claude_md emptied'\n"
        "[ ! -e $d/skills ] && echo 'skills removed'\n"
        "[ ! -e $d/commands ] && echo 'commands removed'\n"
        "[ ! -e $d/agents ] && echo 'agents removed'\n"
        "[ ! -e $d/plans ] && echo 'plans removed'\n"
        "[ ! -e $d/session-env ] && echo 'session-env removed'\n"
        "[ ! -e $d/shell-snapshots ] && echo 'shell-snapshots removed'\n"
        "[ -d $d/plugins/keep-me ] && echo 'plugins preserved'\n"
        "[ -d $d/projects/keep-me ] && echo 'projects preserved'\n"
        "[ -f $d/.claude.json ] && echo 'history preserved'\n"
    )
    result = run_in_sandbox(docker_image, setup)
    assert result.returncode == 0, (
        f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    expected = [
        "claude_md emptied",
        "skills removed",
        "commands removed",
        "agents removed",
        "plans removed",
        "session-env removed",
        "shell-snapshots removed",
        "plugins preserved",
        "projects preserved",
        "history preserved",
    ]
    for line in expected:
        assert line in result.stdout, f"missing: {line}\nfull stdout:\n{result.stdout}"


# =============================================================================
# Validation Recipe Tests (semgrep rule self-tests)
# =============================================================================
#
# These exercise the rule-files-against-themselves workflow:
#   - meta-semgrep : run rules in .semgrep/rules/meta/ against the repo
#   - semgrep-test : `semgrep --test` every rule in .semgrep/rules/ (meta +
#                    python) against its co-located fixtures
#   - validate     : composite of both
#
# semgrep is installed on demand via uvx, so the first run downloads it
# (~75MB). Subsequent runs in the same container are cached.


@pytest.mark.check
def test_just_semgrep_test_passes(docker_image):
    """`just semgrep-test` validates every rule's own test annotations."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just semgrep-test",
    )
    assert result.returncode == 0, (
        f"semgrep-test failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_meta_semgrep_clean_repo_passes(docker_image):
    """`just meta-semgrep` returns 0 on the as-shipped repo (no findings)."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just meta-semgrep",
    )
    assert result.returncode == 0, (
        f"meta-semgrep failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_validate_runs_both_steps(docker_image):
    """`just validate` chains semgrep-test then meta-semgrep."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just validate",
    )
    assert result.returncode == 0, (
        f"validate failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# =============================================================================
# Misc Recipe Tests (default / clean-cache / clean-all / self-check / add-all)
# =============================================================================


@pytest.mark.check
def test_just_default_lists_recipes(docker_image):
    """`just` (no args) runs `default` which delegates to help (`just --list`)."""
    result = run_in_sandbox(docker_image, "just")
    assert result.returncode == 0, (
        f"just default failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The list output should mention at least one known recipe.
    assert "sync-agents" in result.stdout


@pytest.mark.check
def test_just_clean_cache_idempotent_on_missing_dirs(docker_image):
    """`just clean-cache` succeeds even when target cache dirs do not exist."""
    # Fresh container has none of these, so this exercises the "rm -vrf" on
    # missing paths. rc must still be 0.
    result = run_in_sandbox(docker_image, "just clean-cache")
    assert result.returncode == 0, (
        f"clean-cache failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_clean_all_runs_clean_then_clean_cache(docker_image):
    """`just clean-all` is a composite of `clean` + `clean-cache`. Both run."""
    result = run_in_sandbox(docker_image, "just clean-all")
    assert result.returncode == 0, (
        f"clean-all failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Each child recipe prints a distinctive header.
    assert "Remove dotfiles" in result.stdout
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_self_check_succeeds(docker_image):
    """`just self-check` runs doctor + validate-path-duplicates with summary."""
    result = run_in_sandbox(docker_image, "just self-check")
    assert result.returncode == 0, (
        f"self-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Self-check summary:" in result.stdout


@pytest.mark.check
def test_just_add_all_fails_when_dumps_empty(docker_image):
    """`just add-all` is a composite. With empty per-host manifests it must
    fail at the first add-* guard (rc!=0, "missing or empty"), not silently
    succeed. Uses a synthetic dump/testhost/ (ADR 0030), removed again so the
    bind-mounted CI checkout is as clean after the test as before it."""
    script = (
        "mkdir -p dump/testhost && : > dump/testhost/Brewfile "
        "&& : > dump/testhost/gcloud ; "
        "rc=0 && DOTFILES_HOST=testhost just add-all || rc=$? ; "
        "rm -f dump/testhost/Brewfile dump/testhost/gcloud ; "
        "rmdir dump/testhost ; "
        "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0
    assert "missing or empty" in result.stdout


@pytest.mark.check
def test_just_install_runs_mise_install(docker_image):
    """`just install` invokes `mise install` end-to-end and provisions the
    tools listed in mise.toml.

    Inner containers can't reuse MISE_OFFLINE=1 because their cache
    is empty; let mise resolve "latest" online against an
    authenticated GitHub token (CI runs are scoped to 5000/hr).
    """
    result = run_in_sandbox(
        docker_image,
        "mise trust >/dev/null 2>&1; just install",
    )
    assert result.returncode == 0, (
        f"just install failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "mise install" in combined


@pytest.mark.deploy
def test_deploy_provisions_global_mise(docker_image):
    """`just deploy` provisions the host-global mise toolchain.

    The recipe runs `mise -C / install` (cwd=/ so only the global
    config resolves, never a HOME-level project config). We stub
    `mise` to record argv and no-op the install, then assert the
    HOME-independent `-C / install` wiring fired and the symlink
    deploy still happened.
    """
    result = run_in_sandbox(
        docker_image,
        _MISE_RECORD_STUB + "rm -f /tmp/mise-calls.log ~/.zshrc && just deploy && "
        "grep -q -- '-C / install' /tmp/mise-calls.log && "
        "test -L ~/.zshrc",
    )
    assert result.returncode == 0, (
        f"deploy global-mise provisioning wiring failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.deploy
def test_deploy_mise_install_is_global_scoped(docker_image):
    """Guard the `-C /` scope choice: the deploy provisioning command
    must resolve ONLY the global config, never a HOME-level project
    config (`~/mise.toml` / `~/.tool-versions`).

    Plant a sentinel `~/mise.toml`; from cwd=$HOME mise sees it (HOME
    is in scope), but from cwd=/ it must not (HOME is not an ancestor
    of /), while the global config still loads. This locks the
    assumption behind `mise -C / install` so a future "simplification"
    back to `-C "$HOME"` (which would leak HOME-local configs) is
    caught.
    """
    result = run_in_sandbox(
        docker_image,
        'printf \'[tools]\\n"npm:cowsay" = "latest"\\n\' > ~/mise.toml && '
        "mise trust ~/mise.toml >/dev/null 2>&1; "
        # cwd=$HOME sees the planted config (sanity that planting worked):
        'mise -C "$HOME" config 2>&1 | grep -q cowsay && '
        # cwd=/ must NOT see it, yet must still load the global config:
        "! mise -C / config 2>&1 | grep -q cowsay && "
        "mise -C / config 2>&1 | grep -qw uv",
    )
    assert result.returncode == 0, (
        f"global-scope guard failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Dev container is now debian-12 (bookworm) with glibc native — the
# alpine + musl + libc6-compat / gcompat shim era ended with the
# Layer-1 base-image migration. Tests that asserted the shim's
# presence (test_glibc_compat_packages_installed,
# test_glibc_dynamic_loader_present, test_glibc_binary_actually_runs,
# test_dev_container_has_docker_cli via apk) were dropped because the
# debian image has glibc natively and provides docker-cli through the
# devcontainer feature `docker-outside-of-docker`. The corresponding
# regressions can no longer occur on this base.
# ---------------------------------------------------------------------------


@pytest.mark.check
def test_install_sh_has_executable_bit_in_git_index():
    """Anything that clones this repo and execs install.sh directly —
    rather than running 'bash install.sh' — depends on the execute bit.
    If install.sh in the git index has mode 100644 instead of 100755,
    the exec fails with:

      error: script "install.sh" does not have execute permissions

    and the install silently degrades to nothing. Local fs mode is
    irrelevant — what matters is the *index mode*, because that is
    what `git clone` reproduces for whoever does the exec.

    Check it the way they do, with `git ls-files -s`."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "ls-files", "-s", "install.sh"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    # Output format: "<mode> <hash> <stage>\t<path>"
    mode = out.stdout.split()[0]
    assert mode == "100755", (
        f"install.sh git index mode is {mode}, expected 100755.\n"
        "Run: git update-index --chmod=+x install.sh && commit\n"
        "Otherwise a direct exec of the script fails after a clone."
    )


# =============================================================================
# Host-pollution isolation guards (番人)
# =============================================================================
#
# These pin the invariant that produced real host damage earlier (a staged
# `/private/*` secret, a truncated `dump/*`, host `.git/hooks` writes): the
# sandbox must NEVER bind-mount the real repo locally. It must instead mount a
# throwaway copy of ONLY the git-tracked first-party files, and tear it down.
# In CI the runner checkout is itself ephemeral, so the host path is bound
# directly. No Docker is needed to exercise this — we inspect the mount source
# and the snapshot contents, so the guard runs everywhere `just test` runs.


def test_snapshot_excludes_git_untracked_and_submodule_gitlinks(tmp_path):
    """`_snapshot_tracked_worktree` copies only git-tracked first-party files.

    The real `.git`, untracked secrets, and submodule gitlinks must never reach
    the throwaway sandbox checkout.
    """
    # given: a repo with a tracked file, an untracked secret, and a gitlink
    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    _git("init", "-q")
    _git("config", "user.email", "t@e")
    _git("config", "user.name", "t")
    (repo / "tracked.txt").write_text("first-party\n", encoding="utf-8")
    (repo / "private").mkdir()
    (repo / "private" / "secret.key").write_text(
        "SECRET\n", encoding="utf-8"
    )  # untracked
    _git("add", "tracked.txt")
    _git("commit", "-qm", "init")
    # a submodule pointer (gitlink) staged with no checked-out file on disk
    _git(
        "update-index",
        "--add",
        "--cacheinfo",
        "160000,1234567890123456789012345678901234567890,sub",
    )

    # when
    snapshot = _snapshot_tracked_worktree(str(repo))

    # then
    try:
        assert (Path(snapshot) / "tracked.txt").is_file()
        assert not (Path(snapshot) / ".git").exists()
        assert not (Path(snapshot) / "private" / "secret.key").exists()
        assert not (Path(snapshot) / "sub").exists()
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def test_run_in_sandbox_local_mounts_snapshot_not_host(monkeypatch):
    """Locally (no LOCAL_WORKSPACE_FOLDER) the sandbox mounts a throwaway
    git-tracked snapshot, never the host repo, and removes it afterwards."""
    # given: not in CI; the snapshot helper returns a dir we can track
    monkeypatch.delenv("LOCAL_WORKSPACE_FOLDER", raising=False)
    fake_snapshot = tempfile.mkdtemp(prefix="dotfiles-sandbox-test-")
    monkeypatch.setattr(
        sys.modules[__name__],
        "_snapshot_tracked_worktree",
        lambda _src: fake_snapshot,
    )
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_run", _fake_run)

    # when
    run_in_sandbox("img", "echo hi")

    # then: the bind mount SOURCE (left of ':') is the snapshot, not the host
    # repo. Check the source only — the target is always '/root/dotfiles', which
    # equals ROOT inside the dev container, so scanning the whole arg is wrong.
    cmd = captured["cmd"]
    mount_arg = cmd[cmd.index("-v") + 1]
    mount_source = mount_arg.split(":", 1)[0]
    assert mount_source == fake_snapshot
    assert mount_source != str(ROOT)
    # ...and the snapshot is torn down once the run completes
    assert not Path(fake_snapshot).exists()


def test_run_in_sandbox_ci_binds_host_path(monkeypatch):
    """In CI (LOCAL_WORKSPACE_FOLDER set plus the disposable-checkout
    declaration) the sandbox binds the host path directly and must NOT take the
    local snapshot branch. Without the declaration it refuses instead — see
    tests/unit/test_sandbox_mount_fence.py."""
    # given: CI-style env points at a host workspace path it declares disposable
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/work/ci-checkout")
    monkeypatch.setenv(DISPOSABLE_CHECKOUT_ENV, "1")

    def _boom(_src):
        raise AssertionError("must not snapshot in CI mode")

    monkeypatch.setattr(sys.modules[__name__], "_snapshot_tracked_worktree", _boom)
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_run", _fake_run)

    # when
    run_in_sandbox("img", "echo hi")

    # then
    cmd = captured["cmd"]
    mount_arg = cmd[cmd.index("-v") + 1]
    assert mount_arg == "/work/ci-checkout:/root/dotfiles"
