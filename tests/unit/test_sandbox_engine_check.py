"""The dev container tests' engine check (`_docker_available` in
tests/test_just_sandbox.py), with a fake process boundary.

Native rootless Podman, as on the CI runner, prints only `Client` from
`podman version`; the selected engine's version comes from `podman info`, as
.devcontainer/require-podman-socket.sh reads it. Both must be 5 or newer.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sandbox():
    spec = importlib.util.spec_from_file_location(
        "sandbox_engine_check_under_test", ROOT / "tests/test_just_sandbox.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _answers(version=None, info=None, *, version_rc=0, info_rc=0, missing=False):
    """A fake `_run`: what podman prints for `version` and `info`."""
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        if missing:
            raise FileNotFoundError("podman")
        if cmd == ["podman", "version", "--format", "json"]:
            out, rc = version, version_rc
        elif cmd == ["podman", "info", "--format", "json"]:
            out, rc = info, info_rc
        else:
            raise AssertionError(f"unexpected command {cmd}")
        text = out if isinstance(out, str) else json.dumps(out)
        return subprocess.CompletedProcess(cmd, rc, text, "")

    return run, calls


NATIVE = {"Client": {"Version": "5.7.0"}}
REMOTE = {"Client": {"Version": "5.7.0"}, "Server": {"Version": "5.6.2"}}
INFO = {"version": {"Version": "5.6.2"}}


@pytest.mark.parametrize(
    "version, info",
    [
        (NATIVE, INFO),
        (REMOTE, INFO),
        (NATIVE, {"version": {"Version": "6.1.4"}}),
        (NATIVE, {"version": {"Version": "5.6.2-rc1"}}),
        # the engine is what `podman info` reports; `Server` does not decide
        (
            {"Client": {"Version": "5.7.0"}, "Server": {"Version": "4.9.3"}},
            INFO,
        ),
    ],
    ids=["native", "remote", "engine-six", "engine-rc", "remote-old-server-field"],
)
def test_client_and_engine_five_or_newer_pass(sandbox, monkeypatch, version, info):
    run, calls = _answers(version, info)
    monkeypatch.setattr(sandbox, "_run", run)
    assert sandbox._docker_available() is True
    assert ["podman", "info", "--format", "json"] in calls


@pytest.mark.parametrize(
    "version, info, kwargs",
    [
        ({"Client": {"Version": "4.9.3"}}, INFO, {}),
        (NATIVE, {"version": {"Version": "4.9.3"}}, {}),
        (NATIVE, INFO, {"version_rc": 125}),
        (NATIVE, INFO, {"info_rc": 125}),
        ("not json", INFO, {}),
        (NATIVE, "not json", {}),
        ({}, INFO, {}),
        (NATIVE, {"host": {}}, {}),
        (NATIVE, {"version": {"Version": 5}}, {}),
        (NATIVE, {"version": {"Version": "five"}}, {}),
        (NATIVE, INFO, {"missing": True}),
        # remote: `Server` says 5, but the engine `podman info` reports is 4
        (REMOTE, {"version": {"Version": "4.9.3"}}, {}),
        (REMOTE, {"host": {}}, {}),
        # a version string must be whole: major.minor.patch, optional suffix
        ({"Client": {"Version": "5."}}, INFO, {}),
        ({"Client": {"Version": "5.garbage"}}, INFO, {}),
        ({"Client": {"Version": "5.6.2 trailing"}}, INFO, {}),
        (NATIVE, {"version": {"Version": "5."}}, {}),
        (NATIVE, {"version": {"Version": "5.6"}}, {}),
        (NATIVE, {"version": {"Version": "5.6.2 trailing"}}, {}),
    ],
    ids=[
        "old-client",
        "old-engine",
        "version-fails",
        "info-fails",
        "version-not-json",
        "info-not-json",
        "no-client",
        "no-engine-version",
        "engine-version-not-a-string",
        "engine-version-not-a-number",
        "no-podman",
        "remote-old-engine",
        "remote-no-engine-version",
        "client-dot-only",
        "client-garbage",
        "client-trailing",
        "engine-dot-only",
        "engine-two-parts",
        "engine-trailing",
    ],
)
def test_anything_else_is_not_available(sandbox, monkeypatch, version, info, kwargs):
    run, _ = _answers(version, info, **kwargs)
    monkeypatch.setattr(sandbox, "_run", run)
    assert sandbox._docker_available() is False
