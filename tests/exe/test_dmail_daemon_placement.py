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

  workspace VM **host OS systemd** + `docker run --restart=unless-stopped`
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
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAIN_TF = ROOT / "exe" / "coder" / "templates" / "dotfiles-devcontainer" / "main.tf"


@pytest.fixture(scope="module")
def main_tf_text() -> str:
    assert MAIN_TF.is_file(), f"main.tf missing at {MAIN_TF}"
    return MAIN_TF.read_text(encoding="utf-8")


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


def test_dmail_receiver_unit_runs_docker_run(main_tf_text: str) -> None:
    """ExecStart for dmail-receiver must shell out to `docker run`. The
    dmail binary itself ships in an OCI image so the host OS does not
    need a Go toolchain — that decouples upgrades (image tag bump =
    redeploy)."""
    # Look for an ExecStart that invokes docker run inside the
    # dmail-receiver unit body. The heredoc structure means we do not
    # parse INI; instead match an ExecStart line that mentions both
    # docker and the receiver image variable.
    assert re.search(
        r"ExecStart=[^\n]*docker[^\n]*run[^\n]*\$\{var\.dmail_receiver_image\}",
        main_tf_text,
    ), (
        "Expected dmail-receiver unit ExecStart=... docker run "
        "${var.dmail_receiver_image} ... so the image is operator-"
        "pinned and the daemon runs as a separate container "
        "(one-service-per-container)."
    )


def test_dmail_emitter_unit_runs_docker_run(main_tf_text: str) -> None:
    assert re.search(
        r"ExecStart=[^\n]*docker[^\n]*run[^\n]*\$\{var\.dmail_emitter_image\}",
        main_tf_text,
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


@pytest.mark.exe
def test_dmail_units_pass_systemd_analyze() -> None:
    """Heavy: extract each emitted unit file from the heredoc, render
    it with dummy interpolations, run systemd-analyze verify inside
    the ExeStartup container.

    Stubbed out until Phase 2 lands the actual unit body — the static
    checks above are sufficient to RED-pin the placement contract.
    """
    pytest.skip(
        "Phase 2: enable after the systemd unit body lands. The static "
        "checks in this file already pin the placement contract."
    )
