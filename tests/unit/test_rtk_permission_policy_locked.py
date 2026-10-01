"""RTK_HOOK_PERMISSION_DECISION must never be set from tracked settings.

The rtk wrapper's PERMISSION_DECISION_POLICY strips rtk's
`permissionDecision: "allow"` so rewritten commands keep going through the
normal permission flow. That is a security posture the operator decided
(ADR 0047), not a preference: rtk is an output optimiser, not an approver.

The constant reads `RTK_HOOK_PERMISSION_DECISION` as a **test seam**, and any
value other than "strip" restores rtk's auto-allow. So a single line in a
tracked settings fragment — `{"env": {"RTK_HOOK_PERMISSION_DECISION": "keep"}}`
— would silently re-enable blanket auto-approval on every synced machine, with
no code change and nothing in a diff that looks like a permission change.

This module locks that door from both sides:

- a raw scan of every tracked `.claude/settings*.json` (the list comes from
  `git ls-files`, so a settings source added later is covered without anyone
  remembering this file), and
- a structural check of the **composed** env for every claude-family profile x
  OS, which is what sync actually writes into each agent's settings.json.

Both detectors are themselves mutation-tested below, so this file cannot rot
into a test that passes because it stopped looking.

Out of scope by construction: `<agent home>/settings.sync-local.json`, the
machine-local layer. It is untracked and never in a diff, so no repo test can
police it — that is the operator's own machine, and ADR 0047 records that the
variable must not be set there either.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "scripts"))

from sync_agents import (
    AGENTS,
    OS_SETTINGS_OVERLAYS,
    AgentTarget,
    _compose_settings_fragments,
)

POLICY_ENV_VAR = "RTK_HOOK_PERMISSION_DECISION"


def _tracked_settings_sources(root: Path) -> list[Path]:
    """Every tracked Claude settings source, straight from git.

    Enumerating from git rather than a hardcoded list means a new fragment
    (a `settings.shared.linux.json`, another profile) is policed the moment it
    is tracked, without an edit here.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", ".claude/settings*.json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return [root / name for name in out.split("\0") if name]


def _sources_setting_policy(root: Path) -> list[str]:
    """Tracked settings files that mention the policy variable at all.

    Deliberately a substring scan, not a key lookup: the variable must not
    appear in a tracked settings source in ANY position — env value, a
    permissions entry, a statusLine command, anything. For a security posture
    the blunt check is the correct one.
    """
    offenders = []
    for path in _tracked_settings_sources(root):
        if POLICY_ENV_VAR in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(root).as_posix())
    return offenders


def _composed_envs(root: Path, home: Path) -> dict[str, dict]:
    """The env sync would write, per claude-family profile x OS.

    `home` points at a nonexistent directory so the untracked machine-local
    layer is absent and only git-managed layers compose (same probe trick as
    scripts/check_effective_settings.py).
    """
    envs: dict[str, dict] = {}
    for agent in (a for a in AGENTS if a.receives_hooks):
        for system, os_name in OS_SETTINGS_OVERLAYS.items():
            probe = AgentTarget(
                directory=home / "_no-machine-layer",
                name=agent.name,
                key=agent.key,
            )
            composed = _compose_settings_fragments(root, probe, system=system)
            envs[f"{agent.key}-{os_name}"] = (composed or {}).get("env", {})
    return envs


# --- The invariant, on the real repo ---------------------------------------


def test_no_tracked_settings_source_mentions_the_policy_variable() -> None:
    offenders = _sources_setting_policy(ROOT)
    assert offenders == [], (
        f"{POLICY_ENV_VAR} must never be set from tracked settings — it would "
        f"restore rtk's blanket auto-approval on every synced machine "
        f"(ADR 0047). Found in: {offenders}"
    )


def test_composed_env_never_sets_the_policy_variable(tmp_path: Path) -> None:
    """Belt to the scan's braces: check what sync actually writes."""
    envs = _composed_envs(ROOT, tmp_path)
    assert envs, "no claude-family profiles composed — the probe found nothing"
    offenders = {
        name: env[POLICY_ENV_VAR] for name, env in envs.items() if POLICY_ENV_VAR in env
    }
    assert offenders == {}, (
        f"{POLICY_ENV_VAR} reaches a synced settings.json (ADR 0047): {offenders}"
    )


def test_the_wrapper_still_reads_that_variable() -> None:
    """If the seam is ever renamed or dropped, this file must be revisited.

    Without this, renaming the constant would leave two green tests guarding a
    variable nothing reads any more.
    """
    source = (ROOT / "ROOT_AGENTS_hooks_rtk-hook-claude.py").read_text(encoding="utf-8")
    assert POLICY_ENV_VAR in source
    assert 'PERMISSION_DECISION_POLICY == "strip"' in source


# --- Mutation proofs: both detectors must actually fire --------------------


@pytest.fixture()
def repo_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the tracked settings tree, initialised as a repo.

    The scan reads its file list from `git ls-files`, so the copy has to be a
    real repo for the mutation to be visible to it.
    """
    dest = tmp_path / "repo"
    (dest / ".claude" / "settings.profiles").mkdir(parents=True)
    for path in _tracked_settings_sources(ROOT):
        target = dest / path.relative_to(ROOT)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    return dest


def test_repo_copy_is_clean_before_mutation(repo_copy: Path) -> None:
    """Guards the fixture itself: a copy that lost the files proves nothing."""
    assert _tracked_settings_sources(repo_copy), "fixture copied no settings sources"
    assert _sources_setting_policy(repo_copy) == []


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/settings.shared.json",
        ".claude/settings.shared.macos.json",
        ".claude/settings.profiles/work-d.json",
        ".claude/settings.hooks.json",
    ],
)
def test_scan_detects_the_variable_in_any_tracked_source(
    repo_copy: Path, relative: str
) -> None:
    """Inject the variable into each layer; the scan must name that layer."""
    target = repo_copy / relative
    data = json.loads(target.read_text(encoding="utf-8"))
    data.setdefault("env", {})[POLICY_ENV_VAR] = "keep"
    target.write_text(json.dumps(data), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo_copy, check=True)

    assert relative in _sources_setting_policy(repo_copy)


def test_composed_check_detects_a_profile_override(
    repo_copy: Path, tmp_path: Path
) -> None:
    """The composed-env detector fires for a profile-layer injection."""
    target = repo_copy / ".claude" / "settings.profiles" / "work-d.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data.setdefault("env", {})[POLICY_ENV_VAR] = "keep"
    target.write_text(json.dumps(data), encoding="utf-8")

    envs = _composed_envs(repo_copy, tmp_path / "home")
    offenders = [name for name, env in envs.items() if POLICY_ENV_VAR in env]
    assert offenders, "composed-env detector missed a profile-layer override"
    assert all(name.startswith("work-d-") for name in offenders)


def test_composed_check_detects_a_shared_override(
    repo_copy: Path, tmp_path: Path
) -> None:
    """A shared-layer injection reaches every profile x OS."""
    target = repo_copy / ".claude" / "settings.shared.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data.setdefault("env", {})[POLICY_ENV_VAR] = "keep"
    target.write_text(json.dumps(data), encoding="utf-8")

    envs = _composed_envs(repo_copy, tmp_path / "home")
    assert all(POLICY_ENV_VAR in env for env in envs.values())
