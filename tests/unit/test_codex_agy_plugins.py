"""Codex and Antigravity get EGM from `just deploy`, like Claude Code and Pi.

Claude Code and Pi read EGM from their declarations (claude-plugins.json,
pi-packages.json). Codex and Antigravity have none, so codex_agy_plugins.py
follows the Pi pin: Codex's marketplace at the same tag, and Antigravity from
the verified Pi bundle. A machine without the CLI is skipped, not failed.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import codex_agy_plugins as plugins
import install_pi_extensions as installer

TAG = installer.EGM_SOURCE.rpartition("@")[2]
VERSION = TAG.removeprefix("v")
COMMIT = installer.EGM_COMMIT


def _installed(version: str = VERSION, enabled: bool = True) -> dict:
    return {"pluginId": "egm@egm", "version": version, "enabled": enabled}


ADD = [
    ["plugin", "marketplace", "add", plugins.EGM_REPO, "--ref", TAG, "--json"],
    ["plugin", "add", "egm@egm", "--json"],
]
REMOVE = ["plugin", "marketplace", "remove", "egm", "--json"]


@pytest.mark.parametrize(
    ("head", "installed", "steps"),
    [
        (COMMIT, _installed(), []),  # already there
        (None, None, ADD),  # first install
        ("0" * 40, _installed("0.0.9"), [REMOVE, *ADD]),  # a moved tag
        (COMMIT, None, ADD[1:]),  # marketplace there, plugin missing
        (COMMIT, _installed(enabled=False), ADD[1:]),
    ],
)
def test_codex_steps_do_only_what_is_missing(
    head: str | None, installed: dict | None, steps: list[list[str]]
) -> None:
    assert plugins.codex_steps(head, installed, TAG, COMMIT) == steps


class FakeCli:
    """Codex as far as this step sees it: one marketplace checkout and one
    plugin, changed by the commands it runs."""

    def __init__(self, head: str | None, installed: dict | None) -> None:
        self.head, self.installed, self.ran = head, installed, []

    def run(self, args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        tail = args[1:]
        out = ""
        if tail[:3] == ["plugin", "marketplace", "list"]:
            listed = [] if self.head is None else [{"name": "egm", "root": "/egm"}]
            out = json.dumps({"marketplaces": listed})
        elif tail[:2] == ["plugin", "list"]:
            out = json.dumps({"installed": [self.installed] if self.installed else []})
        elif args[:3] == ["git", "-C", "/egm"]:
            out = (self.head or "") + "\n"
        else:
            self.ran.append(args)
            if tail[:3] == ["plugin", "marketplace", "add"]:
                self.head = COMMIT
            if tail[:2] == ["plugin", "add"]:
                self.installed = _installed()
        return subprocess.CompletedProcess(args, 0, stdout=out)


def _which(found: set[str]):
    return lambda name: f"/bin/{name}" if name in found else None


def test_install_moves_codex_to_the_pinned_tag_and_then_has_nothing_to_do(
    tmp_path: Path,
) -> None:
    cli = FakeCli("0" * 40, _installed("0.0.9"))
    plugins.install(tmp_path, which=_which({"codex", "git"}), run=cli.run)
    assert cli.ran == [["/bin/codex", *step] for step in [REMOVE, *ADD]]
    assert plugins.missing(tmp_path, which=_which({"codex", "git"}), run=cli.run) == []


def test_a_machine_without_codex_or_agy_is_skipped(tmp_path: Path) -> None:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        pytest.fail("nothing to run")

    plugins.install(tmp_path, which=_which(set()), run=run)
    assert plugins.missing(tmp_path, which=_which(set()), run=run) == []


def test_agy_installs_the_verified_pi_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified: list[Path] = []
    monkeypatch.setattr(plugins, "verify_egm", verified.append)
    cli = FakeCli(COMMIT, _installed())
    plugins.install(tmp_path, which=_which({"agy"}), run=cli.run)
    bundle = tmp_path / installer.EGM_RELATIVE
    assert verified == [bundle]
    assert cli.ran == [["/bin/agy", "plugin", "install", str(bundle)]]


def test_deploy_runs_this_step_after_pi() -> None:
    deploy = (Path(plugins.__file__).parents[1] / "scripts/deploy.sh").read_text(
        encoding="utf-8"
    )
    steps = deploy[deploy.index("AGENT_STEPS='") :]
    assert steps.index("install_pi_extensions.py") < steps.index(
        "codex_agy_plugins.py codex-agy-plugins-install"
    )
