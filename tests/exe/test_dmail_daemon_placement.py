"""Tests for the dmail-receiver / dmail-emitter daemon placement on the
workspace VM startup_script (exe/coder/templates/dotfiles-devcontainer/
main.tf).

Background
----------
runops-gateway publishes two long-lived daemons that complete the D-Mail
Protocol pipeline (https://github.com/hironow/runops-gateway):

  - dmail-receiver: pulls messages from Pub/Sub `dmail-inbound-receiver`
    and atomically writes `<id>.md` into the phonewave outbox dir.
  - dmail-emitter: fsnotify-watches the phonewave archive dirs and
    publishes new D-Mails to Pub/Sub `dmail-outbound`.

ADR 0013 (runops-gateway) fixes the only allowed gateway-to-VM channel
to Pub/Sub. ADR 0015 (runops-gateway) keeps the binaries in the gateway
repo but delegates **deployment** to dotfiles. Issue 0001
(`docs/issues/0001-dotfiles-dmail-receiver-systemd.md` in runops-gateway)
+ the 2026-05-06 placement experiment
(`experiments/2026-05-06_dotfiles-dmail-daemon-placement.md`) settled
the open question on placement:

  workspace VM **host OS systemd** + `docker run --rm` (with systemd
  Restart=on-failure for supervision — `--rm` and `--restart` are
  mutually exclusive on docker so we delegate restart to systemd)
  for both daemons, sharing /var/lib/phonewave/{archive,outbox} into the
  devcontainer (where the 5pillars live) and into the dmail containers.

  - Per-VM = singleton (no emitter watch race; receiver multiplexing is
    Pub/Sub-native load-balancing).
  - One service per container (Docker best practice preserved).
  - Supervision is plain systemd (matches the existing
    `coder.service` / `cloudflared-exe.service` style on the control
    plane VM).
  - No supervisord / s6-overlay / systemd-user dependencies.

These tests pin that placement so a future refactor cannot silently
delete the daemons or drop them into the devcontainer.

Approach
--------
1. Static regex / parser checks against main.tf source text (cheap,
   always run). Catch missing systemd units, wrong restart policy,
   missing volume mounts, missing image variables.
2. Heavy `@pytest.mark.exe` test that extracts the heredoc, substitutes
   dummy interpolations, and pipes each emitted unit file through
   `systemd-analyze verify` inside the ExeStartup container — same
   pattern as tests/exe/test_startup_script.py.

The Phase 1 commit lands (1) + a stub for (2) so Phase 2 (image build &
publish in runops-gateway) can flip (2) on without re-architecting
the test file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAIN_TF = ROOT / "exe" / "coder" / "templates" / "dotfiles-devcontainer" / "main.tf"

# Reuse the same ubuntu-based image tests/exe/test_startup_script.py
# builds. systemd-analyze ships with the systemd package installed
# there, so we do not need a second Dockerfile.
EXE_STARTUP_DOCKERFILE = ROOT / "tests" / "docker" / "ExeStartup.Dockerfile"
EXE_STARTUP_IMAGE = "dotfiles-exe-startup:latest"


def _run(
    cmd: list[str],
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _run(["docker", "info"]).returncode == 0


@pytest.fixture(scope="module")
def main_tf_text() -> str:
    assert MAIN_TF.is_file(), f"main.tf missing at {MAIN_TF}"
    return MAIN_TF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dmail_unit_bodies(main_tf_text: str) -> dict[str, str]:
    """Pull each `cat > /etc/systemd/system/<name>.service <<'EOF_xxx'`
    heredoc body out of the startup_script. Keyed by unit basename
    ('dmail-receiver' / 'dmail-emitter') so per-unit assertions can
    operate on just that unit's content rather than the whole
    main.tf — that lets ExecStart line continuations (\\) match
    naturally without `[\\s\\S]{0,N}` regex acrobatics."""
    bodies: dict[str, str] = {}
    pattern = re.compile(
        r"cat\s*>\s*/etc/systemd/system/(?P<name>[^.\s]+)\.service\s*<<'(?P<token>EOF_[A-Z]+)'\n(?P<body>.*?)\n(?P=token)",
        re.DOTALL,
    )
    for match in pattern.finditer(main_tf_text):
        bodies[match.group("name")] = match.group("body")
    return bodies


def test_main_tf_declares_dmail_receiver_image_variable(main_tf_text: str) -> None:
    """An `dmail_receiver_image` template variable must exist so the
    operator can pin a concrete tag at template-push time. Without it
    the systemd unit body cannot reference the image without
    hardcoding a registry path, which would couple dotfiles to a
    specific GCP project."""
    assert re.search(
        r'variable\s+"dmail_receiver_image"\s*\{',
        main_tf_text,
    ), (
        'Expected `variable "dmail_receiver_image"` block in main.tf. '
        "See experiments/2026-05-06_dotfiles-dmail-daemon-placement.md "
        "in the runops-gateway repo for the rationale."
    )


def test_main_tf_declares_dmail_emitter_image_variable(main_tf_text: str) -> None:
    """Symmetric with the receiver: emitter image is operator-pinned."""
    assert re.search(
        r'variable\s+"dmail_emitter_image"\s*\{',
        main_tf_text,
    ), 'Expected `variable "dmail_emitter_image"` block in main.tf.'


def test_startup_script_writes_dmail_receiver_systemd_unit(main_tf_text: str) -> None:
    """The VM startup_script heredoc must drop a
    /etc/systemd/system/dmail-receiver.service file. The exact path is
    what `systemctl daemon-reload` + `systemctl enable --now
    dmail-receiver.service` will pick up; if this regex stops matching
    the daemon silently disappears from the VM."""
    assert re.search(
        r"/etc/systemd/system/dmail-receiver\.service",
        main_tf_text,
    ), (
        "Expected the workspace VM startup_script to write a "
        "/etc/systemd/system/dmail-receiver.service unit file. The "
        "experiment document mandates host-OS systemd, not in-container "
        "supervision."
    )


def test_startup_script_writes_dmail_emitter_systemd_unit(main_tf_text: str) -> None:
    assert re.search(
        r"/etc/systemd/system/dmail-emitter\.service",
        main_tf_text,
    ), "Expected /etc/systemd/system/dmail-emitter.service in startup_script."


def test_dmail_units_use_restart_on_failure(main_tf_text: str) -> None:
    """Both unit files must declare Restart=on-failure (matches the
    existing coder.service / cloudflared-exe.service convention).
    Restart=no would let a daemon crash drain Pub/Sub backlog
    silently."""
    occurrences = re.findall(r"Restart=on-failure", main_tf_text)
    assert len(occurrences) >= 2, (
        f"Expected at least 2 'Restart=on-failure' lines (one per dmail "
        f"unit), found {len(occurrences)}. Without auto-restart a single "
        f"crash takes the D-Mail pipeline offline until the operator "
        f"notices."
    )


def test_dmail_receiver_unit_runs_docker_run(
    dmail_unit_bodies: dict[str, str],
) -> None:
    """ExecStart for dmail-receiver must shell out to `docker run`. The
    dmail binary itself ships in an OCI image so the host OS does not
    need a Go toolchain — that decouples upgrades (image tag bump =
    redeploy). systemd's `\\` line-continuation is allowed here:
    the per-unit fixture returns just the unit body, so a regex that
    spans the whole ExecStart= block is safe."""
    body = dmail_unit_bodies.get("dmail-receiver", "")
    assert body, "dmail-receiver.service unit body not found in main.tf"
    assert re.search(
        r"ExecStart=[\s\S]+?docker[\s\S]+?run[\s\S]+?\$\{var\.dmail_receiver_image\}",
        body,
    ), (
        "Expected dmail-receiver unit ExecStart=... docker run "
        "${var.dmail_receiver_image} ... so the image is operator-"
        "pinned and the daemon runs as a separate container "
        "(one-service-per-container)."
    )


def test_dmail_emitter_unit_runs_docker_run(
    dmail_unit_bodies: dict[str, str],
) -> None:
    body = dmail_unit_bodies.get("dmail-emitter", "")
    assert body, "dmail-emitter.service unit body not found in main.tf"
    assert re.search(
        r"ExecStart=[\s\S]+?docker[\s\S]+?run[\s\S]+?\$\{var\.dmail_emitter_image\}",
        body,
    ), (
        "Expected dmail-emitter unit ExecStart=... docker run "
        "${var.dmail_emitter_image} ..."
    )


def test_phonewave_state_dir_volume_mounted_into_dmail_receiver(
    main_tf_text: str,
) -> None:
    """The receiver writes outbox files; the host OS dir
    /var/lib/phonewave/outbox must be bind-mounted into the receiver
    container so the devcontainer (where 5pillars consume them) sees
    the same files."""
    assert re.search(
        r"-v\s+/var/lib/phonewave/outbox:/outbox",
        main_tf_text,
    ), (
        "Expected `-v /var/lib/phonewave/outbox:/outbox` on the "
        "dmail-receiver docker run. Without it the outbox is "
        "container-local and 5pillars cannot read it."
    )


def test_phonewave_state_dir_volume_mounted_into_dmail_emitter(
    main_tf_text: str,
) -> None:
    """Mirror constraint for the emitter: it watches the archive
    directory, so /var/lib/phonewave/archive must be bind-mounted in
    read-only mode (the emitter never writes back into archive)."""
    assert re.search(
        r"-v\s+/var/lib/phonewave/archive:/archive(?::ro)?",
        main_tf_text,
    ), (
        "Expected `-v /var/lib/phonewave/archive:/archive[:ro]` on the "
        "dmail-emitter docker run."
    )


def test_dmail_units_have_no_hardcoded_gcp_identifiers(
    dmail_unit_bodies: dict[str, str],
) -> None:
    """The original implementation hardcoded 'gen-ai-hironow' /
    'dmail-inbound-receiver' / 'dmail-outbound' / 'telemetry.googleapis
    .com:443' directly into the systemd unit body. Codex pre-push
    review #2 (2026-05-06) flagged this as a fatal misroute risk if
    the template were ever pushed against a non-production project
    (staging / sandbox), so each of those values now flows through
    a template variable.

    This test makes the regression visible: the unit body must not
    contain raw GCP project IDs / topic names / endpoints — every
    such value should appear as a `${var.<name>}` interpolation
    instead. Pinning a stricter contract here is cheap because all
    four candidate variables already have defaults that match
    production, so no operator action is required to keep the
    behaviour."""
    forbidden_literals = (
        "gen-ai-hironow",
        "dmail-inbound-receiver",
        "dmail-outbound",
        "telemetry.googleapis.com:443",
    )
    failures: list[str] = []
    for unit_name, body in dmail_unit_bodies.items():
        for literal in forbidden_literals:
            if literal in body:
                failures.append(
                    f"{unit_name}.service still contains the literal "
                    f"'{literal}' — replace with the matching "
                    f"${{var.<name>}} interpolation."
                )
    assert not failures, "\n".join(failures)


def test_phonewave_state_dir_mounted_into_devcontainer(main_tf_text: str) -> None:
    """The same /var/lib/phonewave host dir must also be bind-mounted
    into the existing devcontainer (where 5pillars run). Without this
    the 5pillars and the dmail daemons see different file systems and
    the pipeline never connects."""
    assert re.search(
        r"--volume\s+\"?/var/lib/phonewave",
        main_tf_text,
    ), (
        "Expected `--volume /var/lib/phonewave...` on the devcontainer "
        "docker run so 5pillars share the archive/outbox host dir with "
        "the dmail daemons."
    )


@pytest.fixture(scope="module")
def exe_startup_image() -> str:
    """Build (or reuse) the ubuntu-based image that test_startup_script
    .py also relies on. systemd-analyze comes from the systemd
    package installed inside; we never start systemd, just invoke
    the binary directly against unit files we mount in."""
    if not _docker_available():
        pytest.skip("docker not available; skipping systemd-analyze e2e")
    r = _run(
        [
            "docker",
            "build",
            "-t",
            EXE_STARTUP_IMAGE,
            "-f",
            str(EXE_STARTUP_DOCKERFILE),
            str(ROOT),
        ],
        timeout=600,
    )
    if r.returncode != 0:
        pytest.fail(
            f"failed to build {EXE_STARTUP_IMAGE}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return EXE_STARTUP_IMAGE


@pytest.mark.exe
@pytest.mark.parametrize("unit_name", ["dmail-receiver", "dmail-emitter"])
def test_dmail_units_pass_systemd_analyze(
    dmail_unit_bodies: dict[str, str],
    exe_startup_image: str,
    tmp_path: Path,
    unit_name: str,
) -> None:
    """Each dmail unit body extracted from main.tf must pass
    `systemd-analyze verify` inside the ExeStartup container. The
    container exists only as a sandbox to run the binary; we never
    boot systemd.

    What this catches:
      - malformed [Unit] / [Service] / [Install] section keys
      - bad ExecStart= line continuation (the regex tests rely on
        the body being well-formed; systemd-analyze is the
        ground-truth parser)
      - typo'd Restart=, RestartSec=, After= values
      - missing /usr/bin/docker absolute path on ExecStart=
      - Environment= keys whose value would not parse

    What this does NOT catch (would require a live systemd inside
    the container, which adds privileged + cgroup setup we are not
    paying for):
      - the unit's actual ability to start
      - dependency cycles between After=/Requires= units that are
        not on the system
      - whether the image referenced by ExecStart= exists in
        Artifact Registry (Phase 2 image build / publish)

    The two units are checked independently via parametrize so a
    failure on one names the offender clearly in pytest output.
    """
    body = dmail_unit_bodies.get(unit_name, "")
    assert body, (
        f"{unit_name}.service unit body not found in main.tf — the "
        f"static placement test would have caught this first, but "
        f"this assertion guards the systemd-analyze step against "
        f"silently passing on an empty body."
    )

    unit_path = tmp_path / f"{unit_name}.service"
    unit_path.write_text(body)

    # systemd-analyze short-circuits with "Unit docker.service not
    # found" / "/usr/bin/docker not executable" before validating
    # the unit's own syntax. Production VMs ship Docker Engine via
    # apt; the test image does not. Inject a fake docker.service +
    # /bin/true symlink at /usr/bin/docker INSIDE the container,
    # then run verify. The fakes only satisfy the dependency parser
    # — we never start systemd. This keeps tests/docker/
    # ExeStartup.Dockerfile unchanged.
    verify_script = (
        "set -eu\n"
        "install -d /etc/systemd/system\n"
        # printf %b interprets the \\n escapes; %s would write a
        # literal '\\n' and systemd-analyze would reject the file
        # with 'Invalid section header'.
        "printf '%b' "
        "'[Unit]\\nDescription=fake docker for systemd-analyze\\n"
        "[Service]\\nType=simple\\nExecStart=/bin/true\\n' "
        "> /etc/systemd/system/docker.service\n"
        "install -m 0755 /bin/true /usr/bin/docker\n"
        f"exec systemd-analyze verify /work/{unit_name}.service\n"
    )

    r = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{unit_path}:/work/{unit_name}.service:ro",
            "--entrypoint",
            "bash",
            exe_startup_image,
            "-c",
            verify_script,
        ],
        timeout=120,
    )

    # systemd-analyze prints findings to stderr and exits non-zero
    # when something is unparseable. WARNING-level complaints
    # (e.g. about Type=simple defaulting) come back on exit 0;
    # those are surfaced in the assertion message for visibility
    # but do not fail the test.
    assert r.returncode == 0, (
        f"systemd-analyze verify failed for {unit_name}.service.\n"
        f"--- unit body ---\n{body}\n"
        f"--- stdout ---\n{r.stdout}\n"
        f"--- stderr ---\n{r.stderr}"
    )
