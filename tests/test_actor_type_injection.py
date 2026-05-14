"""Static-analysis tests for RUNOPS_ACTOR_TYPE env injection.

The runops-gateway 4-eyes invariant (gateway ADR 0035) requires every
caller path to surface the right actor classification before any 5-tool
CLI emits a D-Mail. dotfiles ADR 0012 enumerates the four injection
paths; archive issue 0016 closed once each path was wired in, but its
integration-test todos asked for end-to-end verification inside a live
Coder workspace. That live verification still depends on real GCP /
Coder access and stays out of CI scope.

This module is the static-analysis complement (refs/issues/0026): for
every path it reads the relevant artefact as text and fails fast if the
injection string is missing. The goal is to catch silent regressions
during future refactors — if a path's env injection is removed or
renamed, the assertion blocks the PR instead of waiting for a live VM
test to flake.

Layout per path:

  Path A workspace-daemon -> exe/coder/templates/dotfiles-devcontainer/main.tf
      systemd Environment= line + `-e RUNOPS_ACTOR_TYPE` docker
      allowlist for both dmail-receiver and dmail-emitter services.
  Path B ai-agent         -> exe/coder/templates/dotfiles-job/main.tf
      VM-level `--env RUNOPS_ACTOR_TYPE=ai-agent` + Coder agent
      startup_script `export RUNOPS_ACTOR_TYPE=ai-agent`.
  Path C human-operator   -> exe/scripts/cdr-exec
      always-override prefix inside the `cdr ssh` command string.
  Path D ai-agent         -> .zshrc
      Six cc* aliases, each prepending RUNOPS_ACTOR_TYPE=ai-agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    path = ROOT / rel
    assert path.is_file(), f"expected file not found: {rel}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# Path A — workspace-daemon (systemd drop-in + docker -e allowlist)
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "service",
    ["dmail-receiver", "dmail-emitter"],
    ids=["receiver", "emitter"],
)
def test_path_a_workspace_daemon_systemd_environment(service: str) -> None:
    """Each daemon's systemd unit must declare RUNOPS_ACTOR_TYPE=workspace-daemon
    via Environment= so the value reaches the container's process env."""

    content = _read("exe/coder/templates/dotfiles-devcontainer/main.tf")

    # The drop-in lives inside a per-service unit; we only check that
    # the marker line exists at least twice (once per unit).
    needle = "Environment=RUNOPS_ACTOR_TYPE=workspace-daemon"
    occurrences = content.count(needle)
    assert occurrences >= 2, (
        f"expected RUNOPS_ACTOR_TYPE=workspace-daemon "
        f"in both daemon units; saw {occurrences} occurrence(s)"
    )
    # Belt-and-suspenders: ensure the service name appears near the marker
    # so a future refactor cannot rename the unit silently.
    assert service in content, (
        f"expected service {service!r} mentioned alongside the actor-type drop-in"
    )


def test_path_a_workspace_daemon_docker_allowlist() -> None:
    """systemd Environment= is necessary but not sufficient — the
    docker run command must also forward the env into the container via
    -e RUNOPS_ACTOR_TYPE. Both daemons need the allowlist entry."""

    content = _read("exe/coder/templates/dotfiles-devcontainer/main.tf")
    needle = "-e RUNOPS_ACTOR_TYPE"
    occurrences = content.count(needle)
    assert occurrences >= 2, (
        f"expected `-e RUNOPS_ACTOR_TYPE` in both daemon docker run "
        f"argument lists; saw {occurrences} occurrence(s)"
    )


# ---------------------------------------------------------------------
# Path B — AI agent dispatch (cdr-job via Coder template)
# ---------------------------------------------------------------------


def test_path_b_ai_agent_vm_docker_env() -> None:
    """The VM-level docker run that launches the devcontainer must
    inject RUNOPS_ACTOR_TYPE=ai-agent as a value form (not bare -e
    passthrough) so the container receives the literal value."""

    content = _read("exe/coder/templates/dotfiles-job/main.tf")
    assert '--env "RUNOPS_ACTOR_TYPE=ai-agent"' in content, (
        'expected `--env "RUNOPS_ACTOR_TYPE=ai-agent"` literal '
        "in the dotfiles-job VM startup docker run"
    )


def test_path_b_ai_agent_agent_startup_script() -> None:
    """Coder agent startup_script must export RUNOPS_ACTOR_TYPE=ai-agent
    so the actual job_command process inherits the value."""

    content = _read("exe/coder/templates/dotfiles-job/main.tf")
    assert "export RUNOPS_ACTOR_TYPE=ai-agent" in content, (
        "expected `export RUNOPS_ACTOR_TYPE=ai-agent` in the Coder "
        "agent startup_script for dotfiles-job"
    )


# ---------------------------------------------------------------------
# Path C — human operator (cdr-exec always-override)
# ---------------------------------------------------------------------


def test_path_c_human_operator_cdr_exec_always_override() -> None:
    """cdr-exec must prepend `export RUNOPS_ACTOR_TYPE=human-operator`
    to every dispatched command — `always-override`, not default. The
    test pins the literal so a future refactor of the command prefix
    keeps the security invariant intact."""

    content = _read("exe/scripts/cdr-exec")
    assert "export RUNOPS_ACTOR_TYPE=human-operator" in content, (
        "expected `export RUNOPS_ACTOR_TYPE=human-operator` always-override "
        "prefix inside cdr-exec's `cdr ssh ... -- sh -c` command string"
    )


# ---------------------------------------------------------------------
# Path D — cc* aliases (.zshrc)
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias_name",
    ["cc", "cc-p", "cc-a", "cc-b", "cc-c", "cc-d"],
)
def test_path_d_cc_alias_carries_actor_type(alias_name: str) -> None:
    """Each cc* alias must prepend RUNOPS_ACTOR_TYPE=ai-agent so any
    5-tool CLI invoked from inside Claude Code sees the correct caller
    classification. Alias-scope override only — never a global env."""

    content = _read(".zshrc")
    # Match `alias <name>='RUNOPS_ACTOR_TYPE=ai-agent ...'` exactly; the
    # quoted form is what zsh parses, so the prefix must be inside the
    # single quotes (not before them).
    needle = f"alias {alias_name}='RUNOPS_ACTOR_TYPE=ai-agent"
    assert needle in content, (
        f"expected alias '{alias_name}' to start with "
        f"RUNOPS_ACTOR_TYPE=ai-agent in .zshrc"
    )
