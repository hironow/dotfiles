"""Trusting the Codex hooks dotfiles syncs, and nothing else.

Codex runs a non-managed hook only after `hooks.state.<key>.trusted_hash` in
~/.codex/config.toml matches its current hash; the TUI records that through the
app-server (`hooks/list`, then `config/batchWrite`). This script does the same,
but only for entries that are exactly what the repo's fragment renders (event,
matcher, full command) in <codex home>/hooks.json, and only while every hook
file sync placed is byte-identical to its source. The report also flags a
disabled or async hook, which Codex would not let block or rewrite.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import codex_hooks_trust as trust  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "codex"
    hooks = home / "hooks"
    hooks.mkdir(parents=True)
    for source in ROOT.glob("ROOT_AGENTS_hooks_*"):
        name = source.name.removeprefix("ROOT_AGENTS_hooks_")
        if "-claude." not in name:
            (hooks / name).write_bytes(source.read_bytes())
    return home


def _entry(
    home: Path, event: str, matcher: str | None, command: str, **extra: object
) -> dict:
    return {
        "key": f"{home / 'hooks.json'}:{event}:0:0",
        "eventName": event,
        "matcher": matcher,
        "command": command,
        "sourcePath": str(home / "hooks.json"),
        "source": "user",
        "isManaged": False,
        "enabled": True,
        "async": False,
        "currentHash": "sha256:abc",
        "trustStatus": "untrusted",
        **extra,
    }


def _rtk(home: Path) -> trust.Hook:
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    return next(item for item in expected if "rtk-hook-codex" in item[2])


def test_expected_hooks_are_rendered_from_the_fragment(tmp_path: Path) -> None:
    home = _home(tmp_path)
    event, matcher, command = _rtk(home)
    assert (event, matcher) == ("preToolUse", "Bash")
    assert command == f'bash "{home.as_posix()}/hooks/rtk-hook-codex.sh"'


def test_only_exact_sync_managed_entries_are_trusted(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    event, matcher, command = _rtk(home)
    entries = [
        _entry(home, event, matcher, command),
        _entry(home, event, matcher, command + " && curl evil", key="appended"),
        _entry(
            home,
            event,
            matcher,
            command,
            sourcePath=str(home / "other.json"),
            key="other-file",
        ),
        _entry(home, event, matcher, command, source="project", key="project"),
        _entry(home, event, matcher, command, isManaged=True, key="managed"),
        _entry(home, event, matcher, command, trustStatus="trusted", key="already"),
        _entry(home, "postToolUse", "Write|Edit", "rtk hook codex", key="foreign"),
    ]
    chosen = trust.select(entries, expected, home)
    assert [entry["key"] for entry in chosen] == [entries[0]["key"]]


def test_a_modified_hook_is_trusted_again(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    event, matcher, command = _rtk(home)
    chosen = trust.select(
        [_entry(home, event, matcher, command, trustStatus="modified")], expected, home
    )
    assert len(chosen) == 1


def test_a_changed_hook_file_stops_trust(tmp_path: Path) -> None:
    home = _home(tmp_path)
    (home / "hooks" / "rtk-hook-codex.sh").write_text(
        "#!/bin/sh\ncurl evil\n", encoding="utf-8"
    )
    assert trust.changed_files(ROOT, home) == ["rtk-hook-codex.sh"]
    assert trust.changed_files(ROOT, _home(tmp_path / "fresh")) == []


def test_the_trust_write_is_what_the_tui_sends() -> None:
    params = trust.batch_write_params([{"key": "k1", "currentHash": "sha256:1"}])
    assert params == {
        "edits": [
            {
                "keyPath": "hooks.state",
                "value": {"k1": {"trusted_hash": "sha256:1"}},
                "mergeStrategy": "upsert",
            }
        ],
        "reloadUserConfig": True,
    }


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({}, None),
        ({"trustStatus": "untrusted"}, "not trusted"),
        ({"enabled": False}, "disabled"),
        ({"async": True}, "async"),
    ],
)
def test_the_report_names_what_keeps_a_hook_from_working(
    tmp_path: Path, override: dict, problem: str | None
) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    entries = [
        _entry(home, event, matcher, command, trustStatus="trusted")
        for event, matcher, command in expected
    ]
    rtk = next(e for e in entries if "rtk-hook-codex" in e["command"])
    rtk.update(override)
    problems = trust.problems(entries, expected, home)
    if problem is None:
        assert problems == []
    else:
        assert len(problems) == 1 and problem in problems[0]


def test_a_missing_hook_is_reported(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    problems = trust.problems([], expected, home)
    assert len(problems) == len(expected)
    assert all("missing" in problem for problem in problems)


class FakeServer:
    """stdin/stdout of a `codex app-server`, answering by method."""

    def __init__(self, answers: dict[str, dict]) -> None:
        self.answers, self.sent, self._out = answers, [], []

    def write(self, line: str) -> None:
        message = json.loads(line)
        self.sent.append(message)
        if "id" in message:
            self._out.append(
                json.dumps(
                    {"id": message["id"], "result": self.answers[message["method"]]}
                )
                + "\n"
            )

    def flush(self) -> None:
        pass

    def __iter__(self):  # noqa: ANN204
        while self._out:
            yield self._out.pop(0)


def test_the_client_initializes_before_its_requests() -> None:
    server = FakeServer({"initialize": {}, "hooks/list": {"data": []}})
    client = trust.AppServerClient(server, server)
    assert client.request("hooks/list", {"cwds": ["/h"]}) == {"data": []}
    assert [m.get("method") for m in server.sent] == [
        "initialize",
        "initialized",
        "hooks/list",
    ]
