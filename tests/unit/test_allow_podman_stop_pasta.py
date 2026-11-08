"""`.devcontainer/allow-podman-stop-pasta.sh`, run on a temp profile with fake
`sudo`, `journalctl`, `podman`, and `apparmor_parser`; no host is touched.

On Ubuntu 26.04 the passt package's AppArmor profile `pasta` accepts signals
only from unconfined processes, while podman runs under the `podman` label,
so rootless Podman cannot stop pasta (Ubuntu LP #2154379). The script adds
the one rule only when a probe fails with exactly that denial, and proves the
probe passes afterwards.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".devcontainer/allow-podman-stop-pasta.sh"
RULE = "  signal (receive) set=(term) peer=podman,\n"
DENIAL = (
    'audit: type=1400 audit(1762629000.123:456): apparmor="DENIED" '
    'operation="signal" class="signal" profile="pasta" pid=2290 comm="podman" '
    'requested_mask="receive" denied_mask="receive" signal=term peer="podman"'
)
OTHER_DENIAL = DENIAL.replace('profile="pasta"', 'profile="crun"')
TEARDOWN_ERROR = "Error: rootless netns: kill network process: permission denied"
PROFILE = """# vim:syntax=apparmor
abi <abi/4.0>,

include <tunables/global>

profile pasta /usr/bin/pasta{,.avx2} flags=(attach_disconnected) {
  include <abstractions/pasta>

  owner @{HOME}/** rw,
}
"""

# Each probe outcome: exit code, what it prints to stderr, and whether it
# leaves a pasta denial in the journal.
PROBES = {
    "pass": (0, "", None),
    "fail-denial": (125, TEARDOWN_ERROR, DENIAL),
    # podman sometimes prints the teardown error and still exits 0
    "quiet-denial": (0, TEARDOWN_ERROR, DENIAL),
    "fail-other": (1, "Error: something else", None),
    "fail-other-denial": (1, TEARDOWN_ERROR, OTHER_DENIAL),
    "pass-with-denial": (0, "", DENIAL),
    # journald stores the denial only after the script first looks
    "late-denial": (125, TEARDOWN_ERROR, DENIAL),
}
LATE = {"late-denial"}

FAKES = {
    "sudo": """[ "$1" = -n ] || exit 97
shift
printf 'sudo %s\\n' "$*" >> "$FAKE_TRACE"
exec "$@"
""",
    # The journal is one entry per line; an entry's cursor is its line number.
    # Only the exact calls the script makes are answered; anything else is a
    # different query (another transport, -k) and exits 97.
    "journalctl": """count() { n=$(cat "$FAKE_STATE/$1" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_STATE/$1"; echo "$n"; }
lines=$(wc -l < "$FAKE_JOURNAL" | tr -d ' ')
case "$*" in
  '--sync')
    n=$(count sync)
    case " $FAKE_JOURNAL_FAIL " in *" sync$n "*) exit 1 ;; esac
    # a denial journald had not stored yet arrives with the second sync
    if [ "$n" -ge 2 ] && [ -f "$FAKE_STATE/pending" ]; then
      cat "$FAKE_STATE/pending" >> "$FAKE_JOURNAL"
      rm -f "$FAKE_STATE/pending"
    fi
    ;;
  '--no-pager -q -n 1 --show-cursor')
    n=$(count cursor)
    case " $FAKE_JOURNAL_FAIL " in *" cursor$n "*) exit 1 ;; esac
    [ "$lines" -gt 0 ] || exit 0
    tail -n 1 "$FAKE_JOURNAL"
    echo "-- cursor: $lines"
    ;;
  '--no-pager -q --after-cursor='*' _TRANSPORT=kernel _TRANSPORT=audit')
    n=$(count read)
    case " $FAKE_JOURNAL_FAIL " in *" read$n "*) exit 1 ;; esac
    after="${3#--after-cursor=}"
    tail -n "+$((after + 1))" "$FAKE_JOURNAL"
    ;;
  *) exit 97 ;;
esac
""",
    "sleep": """printf 'sleep %s\\n' "$*" >> "$FAKE_TRACE"
""",
    "podman": """[ "$*" = 'unshare --rootless-netns true' ] || exit 97
n=$(cat "$FAKE_STATE/probe" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_STATE/probe"
printf 'probe %s\\n' "$n" >> "$FAKE_TRACE"
outcome=$(printf '%s\\n' "$FAKE_PROBES" | tr ',' '\\n' | sed -n "${n}p")
[ -n "$outcome" ] || exit 98
. "$FAKE_STATE/probe-$outcome"
if [ -n "$denial" ]; then
  if [ "${late:-0}" = 1 ]; then
    printf '%s\\n' "$denial" > "$FAKE_STATE/pending"
  else
    printf '%s\\n' "$denial" >> "$FAKE_JOURNAL"
  fi
fi
[ -z "$message" ] || printf '%s\\n' "$message" >&2
exit "$rc"
""",
    "apparmor_parser": """printf 'apparmor_parser %s\\n' "$*" >> "$FAKE_TRACE"
[ "${FAKE_RELOAD_FAIL:-0}" = 0 ] || exit 1
""",
}


def _run(
    tmp_path,
    *,
    profile=PROFILE,
    probes="fail-denial,pass",
    journal=("kernel: booted",),
    journal_fail="",
    reload_fail=False,
):
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    for directory in (bin_dir, state):
        directory.mkdir()
    for name, body in FAKES.items():
        executable = bin_dir / name
        executable.write_text(
            "#!/bin/sh\nset -eu\n" + body, encoding="utf-8", newline="\n"
        )
        executable.chmod(0o755)
    for name, (rc, message, denial) in PROBES.items():
        (state / f"probe-{name}").write_text(
            f"rc={rc}\nmessage='{message}'\ndenial='{denial or ''}'\n"
            f"late={1 if name in LATE else 0}\n",
            encoding="utf-8",
            newline="\n",
        )
    journal_file = tmp_path / "journal"
    journal_file.write_text(
        "".join(f"{line}\n" for line in journal), encoding="utf-8", newline="\n"
    )
    profile_file = tmp_path / "usr.bin.pasta"
    if profile is not None:
        profile_file.write_text(profile, encoding="utf-8", newline="\n")
    trace = tmp_path / "trace"
    trace.touch()
    bash_dir = Path(resolve_bash()).parent
    directories = [bin_dir, bash_dir, bash_dir.parent / "usr/bin"]
    if os.name != "nt":
        directories += [Path("/usr/bin"), Path("/bin")]
    path = ":".join(bash_path(p) for p in directories)
    result = run_bash(
        SCRIPT,
        bash_path(profile_file),
        cwd=tmp_path,
        env={
            "PATH": path,
            "RUNNER_TEMP": bash_path(tmp_path),
            "FAKE_TRACE": bash_path(trace),
            "FAKE_STATE": bash_path(state),
            "FAKE_JOURNAL": bash_path(journal_file),
            "FAKE_JOURNAL_FAIL": journal_fail,
            "FAKE_PROBES": probes,
            "FAKE_RELOAD_FAIL": "1" if reload_fail else "0",
            "SystemRoot": os.environ.get("SystemRoot", ""),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    after = profile_file.read_text(encoding="utf-8") if profile_file.exists() else None
    return result, trace.read_text(encoding="utf-8").splitlines(), after, profile_file


def _reloads(trace):
    return [line for line in trace if line.startswith("apparmor_parser")]


def _with_rule(profile):
    head, _, tail = profile.rpartition("}\n")
    return head + RULE + "}\n" + tail


def test_a_passing_probe_changes_nothing(tmp_path):
    result, trace, after, _ = _run(tmp_path, probes="pass")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not reproduced on this runner" in result.stdout
    assert after == PROFILE
    assert _reloads(trace) == []
    assert trace.count("probe 1") == 1 and "probe 2" not in trace


@pytest.mark.parametrize("first", ["fail-denial", "quiet-denial"])
def test_the_denial_adds_the_rule_reloads_and_proves_it(tmp_path, first):
    result, trace, after, profile = _run(tmp_path, probes=f"{first},pass")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fixed by the AppArmor rule" in result.stdout
    assert after == _with_rule(PROFILE)
    assert _reloads(trace) == [f"apparmor_parser -r {bash_path(profile)}"]
    assert trace.index("probe 1") < trace.index(_reloads(trace)[0])
    assert trace.index(_reloads(trace)[0]) < trace.index("probe 2")


@pytest.mark.parametrize(
    "rule",
    [
        "  signal (receive) set=(term) peer=podman,\n",
        "  signal (receive, send) set=(term, kill) peer=podman,\n",
        "  signal (receive) peer=podman,\n",
        "  signal peer=podman,\n",
        "  audit signal (receive) set=(term) peer=podman,\n",
    ],
    ids=["exact", "wider-access-and-set", "no-set", "no-access-no-set", "audit"],
)
def test_a_valid_rule_already_there_is_kept_and_reloaded(tmp_path, rule):
    profile = PROFILE.replace(
        "  owner @{HOME}/** rw,\n", "  owner @{HOME}/** rw,\n" + rule
    )
    result, trace, after, _ = _run(tmp_path, profile=profile)
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == profile
    # a run after a failed reload must reload, not trust the file
    assert len(_reloads(trace)) == 1


@pytest.mark.parametrize(
    "rule",
    [
        "  # signal (receive) set=(term) peer=podman,\n",
        "  signal (send) set=(term) peer=podman,\n",
        "  signal (receive) set=(kill) peer=podman,\n",
        "  deny signal (receive) set=(term) peer=podman,\n",
        "  signal (receive) set=(term) peer=unconfined,\n",
        "  signal (receive) set=(term) peer=podman-helper,\n",
    ],
    ids=["comment", "send-only", "kill-only", "deny", "other-peer", "longer-peer"],
)
def test_a_rule_that_does_not_allow_it_gets_the_rule_added(tmp_path, rule):
    profile = PROFILE.replace(
        "  owner @{HOME}/** rw,\n", "  owner @{HOME}/** rw,\n" + rule
    )
    result, trace, after, _ = _run(tmp_path, profile=profile)
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == _with_rule(profile)
    assert len(_reloads(trace)) == 1


def test_a_valid_rule_in_a_child_profile_does_not_count(tmp_path):
    child = "  profile helper {\n    signal (receive) set=(term) peer=podman,\n  }\n"
    profile = PROFILE.replace(
        "  owner @{HOME}/** rw,\n", "  owner @{HOME}/** rw,\n" + child
    )
    result, _, after, _ = _run(tmp_path, profile=profile)
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == _with_rule(profile)


@pytest.mark.parametrize(
    "probes,journal",
    [
        ("fail-other", ("kernel: booted",)),
        ("fail-other-denial", ("kernel: booted",)),
        # a denial from before the probe is not evidence about the probe
        ("fail-other", ("kernel: booted", DENIAL)),
    ],
    ids=["no-denial", "other-profile", "denial-before-the-cursor"],
)
def test_another_failure_changes_nothing_and_stops(tmp_path, probes, journal):
    result, trace, after, _ = _run(tmp_path, probes=probes, journal=journal)
    assert result.returncode != 0, result.stdout
    assert after == PROFILE
    assert _reloads(trace) == []
    assert "fixed" not in result.stdout and "not reproduced" not in result.stdout


def test_no_profile_file_stops_when_the_probe_fails(tmp_path):
    result, trace, after, _ = _run(tmp_path, profile=None)
    assert result.returncode != 0
    assert after is None and _reloads(trace) == []


def test_no_profile_file_is_fine_when_the_probe_passes(tmp_path):
    result, _, after, _ = _run(tmp_path, profile=None, probes="pass")
    assert result.returncode == 0, result.stdout + result.stderr
    assert after is None


@pytest.mark.parametrize("failing", ["cursor1", "read1", "cursor2", "read2"])
def test_a_journal_read_that_fails_is_never_no_denial(tmp_path, failing):
    result, trace, _, _ = _run(tmp_path, journal_fail=failing)
    assert result.returncode != 0, result.stdout
    assert "fixed" not in result.stdout and "not reproduced" not in result.stdout
    if failing == "cursor1":
        assert "probe 1" not in trace


def test_an_empty_journal_gives_no_cursor_and_stops(tmp_path):
    result, trace, _, _ = _run(tmp_path, journal=())
    assert result.returncode != 0
    assert "probe 1" not in trace


def test_a_profile_not_ending_in_a_brace_stops_unchanged(tmp_path):
    profile = PROFILE.rstrip("}\n") + "\n"
    result, trace, after, _ = _run(tmp_path, profile=profile)
    assert result.returncode != 0
    assert after == profile and _reloads(trace) == []


@pytest.mark.parametrize(
    "probes,reload_fail",
    [
        ("fail-denial,pass", True),
        ("fail-denial,fail-denial", False),
        ("fail-denial,pass-with-denial", False),
    ],
    ids=["reload-fails", "probe-still-fails", "new-denial-after"],
)
def test_no_proof_after_the_change_stops(tmp_path, probes, reload_fail):
    result, _, _, _ = _run(tmp_path, probes=probes, reload_fail=reload_fail)
    assert result.returncode != 0, result.stdout
    assert "fixed" not in result.stdout


def _reads(trace):
    return [
        line
        for line in trace
        if line.startswith("sudo journalctl --no-pager -q --after-cursor=")
    ]


def test_a_denial_that_reaches_the_journal_late_still_gets_the_rule(tmp_path):
    result, trace, after, _ = _run(tmp_path, probes="late-denial,pass")
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == _with_rule(PROFILE)
    assert len(_reloads(trace)) == 1
    assert "fixed by the AppArmor rule" in result.stdout


def test_every_read_follows_a_sync_and_no_denial_is_concluded_after_retries(tmp_path):
    result, trace, _, _ = _run(tmp_path, probes="fail-other")
    assert result.returncode != 0
    syncs = [i for i, line in enumerate(trace) if line == "sudo journalctl --sync"]
    reads = [i for i, line in enumerate(trace) if line in _reads(trace)]
    assert len(reads) == 5 and len(syncs) == 5, trace
    assert all(sync < read for sync, read in zip(syncs, reads, strict=True))
    assert [line for line in trace if line.startswith("sleep")] == ["sleep 1"] * 4


@pytest.mark.parametrize(
    "failing",
    # the first read finds the denial, so the second sync precedes the proof
    ["sync1", "sync2"],
    ids=["before-the-first-read", "before-the-proof"],
)
def test_a_journal_sync_that_fails_stops(tmp_path, failing):
    result, _, _, _ = _run(tmp_path, probes="fail-denial,pass", journal_fail=failing)
    assert result.returncode != 0, result.stdout
    assert "fixed" not in result.stdout and "not reproduced" not in result.stdout


def test_a_profile_without_a_final_newline_gets_one(tmp_path):
    result, _, after, _ = _run(tmp_path, profile=PROFILE.rstrip("\n"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == _with_rule(PROFILE)
