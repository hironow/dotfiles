"""Public GC scripts with process/clock/engine I/O fakes, never copied selectors.

Every engine boundary checks actual deletion witnesses with an independent
arbitrary-precision oracle. Failed assertions include the seed and full trace.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
JQ = shutil.which("jq")


def resolve_pwsh(environ, which=shutil.which):
    """The PowerShell the replays run: PODMAN_GC_TEST_PWSH, else pwsh on PATH.

    An override that is not an executable stops the run; it never turns the
    PowerShell cases into skips.
    """
    override = environ.get("PODMAN_GC_TEST_PWSH")
    if override is None:
        return which("pwsh")
    found = which(override)
    if found is None:
        raise RuntimeError(f"PODMAN_GC_TEST_PWSH={override!r} is not an executable")
    return found


PWSH = resolve_pwsh(os.environ)
IMAGE = "a" * 64
PARENT = "b" * 64
NOW = "2030-01-01T00:00:00Z"
OLD = "2020-01-01T00:00:00Z"

FAKE = r"""
import datetime, json, os, re, sys
from pathlib import Path
p = Path(os.environ['GC_STATE'])
s = json.loads(p.read_text(encoding='utf-8'))
a = sys.argv[1:]
s['trace'].append(a)
def identity(value):
    # Wire adapter/oracle identity only. This never selects candidates.
    if not isinstance(value, str) or not re.fullmatch(r'(sha256:)?[a-f0-9]{64}', value):
        raise ValueError('invalid image identity')
    return value.removeprefix('sha256:')
def expected_cutoff():
    # Independent Python arbitrary precision, not the production conversion.
    raw = os.environ['RUNNER_GC_RETENTION']
    if not re.fullmatch(r'[0-9]+[smhd]?', raw): raise ValueError('invalid retention')
    clock = s.get('clock', '1893456000')
    if s.get('clock_error') or not re.fullmatch(r'[0-9]+', clock): raise ValueError('invalid clock')
    now = int(clock)
    if now > 2**63 - 1: raise ValueError('clock outside signed arithmetic')
    unit = raw[-1] if raw[-1].isalpha() else 's'
    seconds = int(raw[:-1] if raw[-1].isalpha() else raw) * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
    if seconds > now: raise ValueError('retention before epoch')
    return now - seconds

def check_age(witness):
    created = datetime.datetime.fromisoformat(witness['Created'])
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    delta = created - epoch
    assert delta.days * 86400 + delta.seconds < expected_cutoff()

def done(value='', rc=0):
    # Check witnesses after EVERY engine I/O, including refused removals.
    for iid in s['removed']:
        try:
            assert not any(identity(c['Image']) == iid for c in s['containers'].values())
            assert not s.get('foreign_job')
            witness = s['deleted_metadata'][iid]
            assert identity(witness['Id']) == iid
            assert isinstance(witness['RepoTags'], list)
            assert all(isinstance(t, str) and t for t in witness['RepoTags'])
            check_age(witness)
            prefix = os.environ['RUNNER_GC_KEEP_TAG_PREFIX'].removeprefix('localhost/')
            assert not any(t.removeprefix('localhost/').startswith(prefix) for t in witness['RepoTags'])
        except (AssertionError, KeyError, TypeError, ValueError):
            s['violations'].append('DeletePrecondition/Age/Metadata/ObservedKeep/Reference/ForeignJob')
    for cid in s['removed_containers']:
        try:
            witness = s['deleted_container_metadata'][cid]
            assert witness['Id'] == cid
            assert witness['State']['Status'] in ['exited', 'created', 'stopped']
            check_age(witness)
            assert not s.get('foreign_job')
        except (AssertionError, KeyError, TypeError, ValueError):
            s['violations'].append('ContainerDeletePrecondition/Age/Metadata/ForeignJob')
    if s.get('protected_parent') and s['protected_parent'] not in s['images']:
        s['violations'].append('ParentProtection')
    p.write_text(json.dumps(s), encoding='utf-8')
    print(value)
    sys.exit(rc)
if a[:1] == ['owner-reentry']:
    s['owner_reentry'] = a[1:]
    done()
if a[:1] == ['--version']: done('podman version ' + s.get('client', '6.1.4'))
if a[:1] == ['info']:
    done(json.dumps(s.get('info', {'version': {'Version': s.get('server', '5.6.2'), 'APIVersion': '5.6.2'},
                     'host': {'serviceIsRemote': False}})))
if a[:1] == ['ps']:
    if s.get('container_enumeration_error'): done(rc=1)
    done('\n'.join(s['containers']))
if a[:1] == ['images']:
    if s.get('image_enumeration_error'): done(rc=1)
    done('\n'.join(s.get('enumeration_ids', list(s['images']))))
if a[:2] == ['container', 'inspect']:
    cid = a[-1]
    if cid not in s['containers'] or s.get('reference_error'): done(rc=1)
    done(json.dumps([s['containers'][cid]]))
if a[:2] == ['image', 'inspect']:
    try: iid = identity(a[-1])
    except ValueError: done(rc=1)
    if iid not in s['images']: done(rc=1)
    s['reads'][iid] = s['reads'].get(iid, 0) + 1
    img = s['images'][iid]
    if s['reads'][iid] >= 2 and s.get('late_keep'):
        img['RepoTags'] = ['ordinary:latest', 'localhost/keep/model:latest']
    if s['reads'][iid] >= 2 and s.get('late_invalid'): img['Created'] = 'invalid'
    if s.get('inspect_error'): done(rc=1)
    done(json.dumps(img if s.get('object_inspect') else [img]))
if a[:1] == ['rmi']:
    iid = identity(a[-1])
    if a != ['rmi', '--no-prune', a[-1]]:
        s['unsafe'].append(a)
        done(rc=1)
    if s['reads'].get(iid, 0) < 2 or s['trace'][-2] != ['image', 'inspect', a[-1]]:
        s['violations'].append('missing immediate final inspection')
    if s.get('new_reference'):
        s['containers']['cafe'] = {'Id': 'cafe', 'Image': 'sha256:' + iid,
            'Created': '2020-01-01T00:00:00Z', 'State': {'Status': 'running'}}
    if any(identity(c['Image']) == iid for c in s['containers'].values()) or len(s['images'][iid]['RepoTags']) > 1:
        s['refused'].append(iid)
        done(rc=1)
    s['removed'].append(iid)
    s['deleted_metadata'][iid] = s['images'][iid]
    del s['images'][iid]
    done()
if a[:1] == ['rm']:
    cid = a[-1]
    if a != ['rm', cid] or s['containers'][cid]['State']['Status'] not in ['exited', 'created', 'stopped']:
        s['unsafe'].append(a)
        done(rc=1)
    s['removed_containers'].append(cid)
    s['deleted_container_metadata'][cid] = s['containers'][cid]
    del s['containers'][cid]
    done()
s['unsafe'].append(a)
done(rc=1)
"""


def inventory(**overrides):
    state = {
        "images": {
            IMAGE: {
                "Id": "sha256:" + IMAGE,
                "Created": OLD,
                "RepoTags": ["ordinary:latest"],
            }
        },
        "enumeration_ids": ["sha256:" + IMAGE],
        "containers": {},
        "trace": [],
        "reads": {},
        "unsafe": [],
        "removed": [],
        "removed_containers": [],
        "refused": [],
        "violations": [],
        "deleted_metadata": {},
        "deleted_container_metadata": {},
    }
    state.update(overrides)
    return state


def container(*, reference="sha256:" + IMAGE, created=OLD, status="running"):
    return {
        "Id": "def",
        "Image": reference,
        "Created": created,
        "State": {"Status": status},
    }


def replay(
    tmp_path,
    state,
    *,
    legacy=False,
    dry=False,
    busy=False,
    prefix="keep/",
    owner=False,
    jq_fail=False,
    retention="2h",
):
    assert JQ is not None, "required jq missing; cannot verify GC simulation"
    tmp_path.mkdir(parents=True, exist_ok=True)
    state_path = tmp_path / "state.json"
    state["foreign_job"] = bool(busy and busy != "own")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    fake = tmp_path / "engine.py"
    fake.write_text(FAKE, encoding="utf-8")
    env_file = tmp_path / "io.sh"
    env_file.write_text(
        f'''podman() {{ "{bash_path(Path(sys.executable))}" "{bash_path(fake)}" "$@"; }}
docker() {{ echo FORBIDDEN-docker >&2; exit 91; }}
jq() {{
  if [ "${{JQ_FAIL:-0}}" = "1" ] && [ "$*" = '-r .RepoTags[]' ]; then return 1; fi
  "{bash_path(Path(JQ))}" "$@"
}}
uname() {{ echo Linux; }}
id() {{ echo {0 if owner else 1000}; }}
stat() {{ case "$*" in *%U*) echo runner ;; *%u*) echo 1234 ;; *) exit 91 ;; esac; }}
getent() {{ echo 'runner:x:1234:1234:runner:/disposable/runner:/bin/bash'; }}
df() {{ printf 'header\\nfake fake fake fake fake\\n'; }}
pgrep() {{ {"echo $$" if busy == "own" else "echo 999999" if busy else "return 1"}; }}
ps() {{ echo 1; }}
date() {{
  case "$*" in
    +%s) printf '%s\\n' '{state.get("clock", "1893456000")}'; return {1 if state.get("clock_error") else 0} ;;
    *-d*) case "$*" in
      *2020-01-01T00:00:00*) echo 1577836800 ;;
      *2030-01-01T00:00:00*) echo 1893456000 ;;
      *2029-12-31T21:59:59*) echo 1893448799 ;;
      *2029-12-31T22:00:00*) echo 1893448800 ;;
      *2029-12-31T22:00:01*) echo 1893448801 ;;
      *) return 1 ;;
    esac ;;
    *) echo simulated ;;
  esac
}}
rm() {{ echo FORBIDDEN-rm >&2; exit 91; }}
runuser() {{ {'podman owner-reentry "$@"' if owner else "exit 91"}; }}
apt-get() {{ {"return 0" if owner else "exit 91"}; }}
journalctl() {{ {"return 0" if owner else "exit 91"}; }}
fstrim() {{ {"return 1" if owner else "exit 91"}; }}
''',
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bash_dir = Path(resolve_bash()).parent
    safe_path = ":".join(
        bash_path(p)
        for p in (bash_dir, bash_dir.parent / "usr/bin", Path("/usr/bin"), Path("/bin"))
    )
    env = {
        "PATH": safe_path,
        "HOME": str(home),
        "BASH_ENV": bash_path(env_file),
        "GC_STATE": str(state_path),
        "RUNNER_GC_KEEP_TAG_PREFIX": prefix,
        "RUNNER_GC_DRY_RUN": "1" if dry else "0",
        "JQ_FAIL": "1" if jq_fail else "0",
        "RUNNER_GC_RETENTION": retention,
        "RUNNER_GC_DOCKER_ONLY" if legacy else "RUNNER_GC_PODMAN_ONLY": "1",
    }
    if legacy:
        env["RUNNER_GC_PODMAN_ONLY"] = "0"
    if owner:
        env.pop("RUNNER_GC_PODMAN_ONLY", None)
        runner = tmp_path / "synthetic-runner"
        runner.mkdir()
        env["RUNNER_GC_ROOT"] = str(runner)
    proc = run_bash(
        ROOT / "scripts/runner_gc.sh",
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    final = json.loads(state_path.read_text(encoding="utf-8"))
    assert proc.returncode == 0, (proc.stdout, proc.stderr, final)
    assert final["violations"] == [], final
    assert final["unsafe"] == [], final
    return final


def replay_powershell(
    tmp_path,
    state,
    *,
    dry=False,
    legacy_skip=False,
    timeout=False,
    busy=False,
    prefix="keep/",
    retention="2h",
):
    """Whole script, with only process/clock I/O overridden; never selectors."""
    assert PWSH is not None
    tmp_path.mkdir(parents=True, exist_ok=True)
    state_path = tmp_path / "state.json"
    state["foreign_job"] = bool(busy and busy != "own")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    engine = tmp_path / "engine.py"
    engine.write_text(FAKE, encoding="utf-8")
    wrapper = tmp_path / "replay.ps1"
    quote = lambda value: str(value).replace("'", "''")
    switches = "-DryRun" if dry else ""
    if legacy_skip:
        switches += " -SkipDocker"
    wrapper.write_text(
        f"""$ErrorActionPreference = 'Stop'
function Get-Date {{
    param($Format)
    if ($Format) {{ return 'simulated' }}
    {"throw 'clock query failed'" if state.get("clock_error") else ""}
    return [DateTimeOffset]::Parse('{state.get("ps_clock", NOW)}').UtcDateTime
}}
function Get-Command {{ return @{{ Name = 'podman' }} }}
function Get-CimInstance {{ return @{{ ParentProcessId = 0 }} }}
function Get-Process {{ {"return @([pscustomobject]@{ Id = $PID })" if busy == "own" else "return @([pscustomobject]@{ Id = 999999 })" if busy else "return @()"} }}
function taskkill {{ [IO.File]::WriteAllText('{quote(tmp_path / "killed")}', ($args -join ' ')) }}
function Start-Process {{
    param($FilePath, $ArgumentList, [switch]$NoNewWindow, [switch]$PassThru,
          $RedirectStandardOutput, $RedirectStandardError)
    if ($FilePath -ne 'podman') {{ throw 'Unexpected executable' }}
    $code = 0
    if (-not ${str(timeout).lower()}) {{
        $output = & '{quote(sys.executable)}' '{quote(engine)}' @ArgumentList
        $code = $LASTEXITCODE
        [IO.File]::WriteAllText($RedirectStandardOutput, ($output -join "`n"))
    }}
    $process = [pscustomobject]@{{ Id = 12345; ExitCode = $code }}
    $process | Add-Member ScriptMethod WaitForExit {{ param($budget) return (-not ${str(timeout).lower()}) }}
    $process | Add-Member ScriptMethod Refresh {{ }}
    $process | Add-Member ScriptMethod Dispose {{ }}
    return $process
}}
& '{quote(ROOT / "scripts/runner_gc_win.ps1")}' -PodmanOnly -PodmanTimeoutSec 1 {switches}
""",
        encoding="utf-8",
    )
    env = {
        "PATH": os.defpath,
        "GC_STATE": str(state_path),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "RUNNER_GC_KEEP_TAG_PREFIX": prefix,
        "RUNNER_GC_RETENTION": retention,
    }
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    final = json.loads(state_path.read_text(encoding="utf-8"))
    assert proc.returncode == 0 and not proc.stderr, (proc.stdout, proc.stderr, final)
    assert final["violations"] == [], final
    assert final["unsafe"] == [], final
    return final


def powershell_identity(pwsh):
    """Version and edition, from the runtime itself."""
    proc = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "'{0} {1}' -f $PSVersionTable.PSVersion, $PSVersionTable.PSEdition",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0 and not proc.stderr, (pwsh, proc.stdout, proc.stderr)
    return proc.stdout.strip()


@pytest.fixture(scope="module", autouse=True)
def report_powershell_runtime(request):
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    line = (
        "PowerShell GC replays: none (no PODMAN_GC_TEST_PWSH, no pwsh on PATH)"
        if PWSH is None
        else f"PowerShell GC replays: {PWSH} {powershell_identity(PWSH)}"
    )
    if reporter is not None:
        reporter.write_line(line)
    else:
        print(line)


def run_platform(platform, tmp_path, state, **kwargs):
    if platform == "powershell":
        if PWSH is None:
            pytest.skip(
                "PowerShell runtime absent; public-script replay unverified here"
            )
        return replay_powershell(tmp_path, state, **kwargs)
    return replay(tmp_path, state, **kwargs)


def test_public_gc_uses_nonforced_no_parent_prune(tmp_path):
    assert replay(tmp_path, inventory(), legacy=True)["removed"] == [IMAGE]


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize(
    "enum_prefix,inspect_prefix",
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_native_full_image_identity_collects(
    tmp_path, platform, enum_prefix, inspect_prefix
):
    state = inventory(enumeration_ids=[("sha256:" if enum_prefix else "") + IMAGE])
    state["images"][IMAGE]["Id"] = ("sha256:" if inspect_prefix else "") + IMAGE
    final = run_platform(platform, tmp_path, state)
    assert final["removed"] == [IMAGE], final  # Positive collection, never retain-all.


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("reference", [IMAGE, "sha256:" + IMAGE])
def test_mixed_native_reference_protection(tmp_path, platform, reference):
    state = inventory(
        enumeration_ids=["sha256:" + IMAGE],
        containers={"def": container(reference=reference)},
    )
    state["images"][IMAGE]["Id"] = IMAGE
    final = run_platform(platform, tmp_path, state)
    assert final["removed"] == final["removed_containers"] == [], final
    assert not any(cmd[0] == "rmi" for cmd in final["trace"]), final


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("field", ["enumeration", "inspect", "reference"])
@pytest.mark.parametrize(
    "value", ["abc", "sha256:abc", "sha512:" + IMAGE, "A" * 64, "sha256:" + IMAGE + "0"]
)
def test_malformed_or_different_full_image_identity_retained(
    tmp_path, platform, field, value
):
    state = inventory()
    if field == "enumeration":
        state["enumeration_ids"] = [value]
    elif field == "inspect":
        state["images"][IMAGE]["Id"] = value
    else:
        state["containers"]["def"] = container(reference=value)
    final = run_platform(platform, tmp_path, state)
    assert final["removed"] == final["removed_containers"] == [], final


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("created", [OLD, NOW])
@pytest.mark.parametrize(
    "retention",
    [
        "5124095576030431h",
        "9" * 100 + "h",
        "9" * 100 + "m",
        "9" * 100 + "d",
        "9" * 100 + "s",
        "1893456001s",
        "-1h",
        "bad",
        "1.5h",
        "7200s\n",
    ],
)
def test_invalid_or_excessive_retention_retains_both_inventories(
    tmp_path, platform, created, retention
):
    state = inventory(containers={"def": container(created=created, status="exited")})
    state["images"][IMAGE]["Created"] = created
    final = run_platform(platform, tmp_path, state, retention=retention)
    assert final["removed"] == final["removed_containers"] == [], final
    assert not any(cmd[0] in {"rm", "rmi"} for cmd in final["trace"]), final


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize(
    "retention", ["08h", "0007200s", "000120m", "0001d", "0", "000s", "7200"]
)
def test_decimal_leading_zeros_and_explicit_zero_collect(tmp_path, platform, retention):
    state = inventory(containers={"def": container(status="exited")})
    final = run_platform(platform, tmp_path, state, retention=retention)
    assert final["removed"] == [IMAGE] and final["removed_containers"] == ["def"], final


@pytest.mark.parametrize(
    "clock,error",
    [
        ("bad", False),
        ("-1", False),
        ("9223372036854775808", False),
        ("9" * 100, False),
        ("", False),
        ("1893456000", True),
    ],
)
def test_invalid_clock_retains_both_inventories(tmp_path, clock, error):
    state = inventory(
        clock=clock, clock_error=error, containers={"def": container(status="exited")}
    )
    final = replay(tmp_path, state)
    assert final["removed"] == final["removed_containers"] == [], final


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("retention", ["1893456000s", "31557600m", "525960h", "21915d"])
def test_retention_reaching_unix_epoch_retains_old_resources(
    tmp_path, platform, retention
):
    state = inventory(containers={"def": container(status="exited")})
    final = run_platform(platform, tmp_path, state, retention=retention)
    assert final["removed"] == final["removed_containers"] == [], final


@pytest.mark.parametrize("clock", ["0001893456000", "9223372036854775807", "0"])
def test_valid_decimal_clock_bounds(tmp_path, clock):
    final = replay(tmp_path, inventory(clock=clock), retention="0")
    assert final["removed"] == ([IMAGE] if int(clock) > 1577836800 else []), final


@pytest.mark.parametrize(
    "tags,prefix",
    [
        (["localhost/keep/model:latest"], "keep/"),
        (["ordinary:latest", "localhost/keep/model:latest"], "keep/"),
        (["keep/model:latest"], "localhost/keep/"),
        (["localhost/archive/model:latest"], "archive/"),
        (["registry.example/archive/model:latest"], "registry.example/archive/"),
    ],
)
def test_observed_keep_alias_protects_whole_image(tmp_path, tags, prefix):
    state = inventory()
    state["images"][IMAGE]["RepoTags"] = tags
    assert replay(tmp_path, state, prefix=prefix)["removed"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("Created", "invalid"),
        ("Created", ""),
        ("Created", None),
        ("Created", NOW),
        ("RepoTags", None),
        ("RepoTags", "keep/model:latest"),
        ("RepoTags", [None]),
        ("RepoTags", ["ordinary:latest", 3]),
    ],
)
def test_invalid_image_metadata_retained(tmp_path, field, value):
    state = inventory()
    state["images"][IMAGE][field] = value
    assert replay(tmp_path, state)["removed"] == []


@pytest.mark.parametrize(
    "fault",
    [
        "container_enumeration_error",
        "image_enumeration_error",
        "inspect_error",
        "reference_error",
        "new_reference",
        "late_keep",
        "late_invalid",
        "object_inspect",
    ],
)
def test_reference_and_metadata_failures_retain_images(tmp_path, fault):
    state = inventory(**{fault: True})
    if fault == "reference_error":
        state["containers"]["def"] = container()
    final = replay(tmp_path, state)
    assert final["removed"] == [], final
    if fault == "new_reference":
        assert final["refused"] == [IMAGE] and "cafe" in final["containers"], final


@pytest.mark.parametrize(
    "field,value",
    [
        ("Id", "wrong"),
        ("Image", None),
        ("Image", "not-an-id"),
        ("Created", None),
        ("State", {}),
        ("State", {"Status": "unknown"}),
    ],
)
def test_invalid_reference_metadata_retains_images(tmp_path, field, value):
    item = container()
    item[field] = value
    final = replay(tmp_path, inventory(containers={"def": item}))
    assert final["removed"] == final["removed_containers"] == [], final


def test_multitag_refusal_does_not_escalate(tmp_path):
    state = inventory()
    state["images"][IMAGE]["RepoTags"] = ["one:latest", "two:latest"]
    assert replay(tmp_path, state)["refused"] == [IMAGE]


@pytest.mark.parametrize("dry,busy", [(True, False), (False, True)])
def test_dry_run_and_foreign_job_do_not_delete(tmp_path, dry, busy):
    final = replay(tmp_path, inventory(), dry=dry, busy=busy)
    assert final["removed"] == final["removed_containers"] == [], final
    if busy:
        assert final["trace"] == [], final


@pytest.mark.parametrize(
    "client,server",
    [("4.9.0", "5.6.2"), ("6.1.4", "4.9.0"), ("bad", "5.6.2"), ("6.1.4", "bad")],
)
def test_cli_and_server_versions_checked_separately(tmp_path, client, server):
    assert replay(tmp_path, inventory(client=client, server=server))["removed"] == []


@pytest.mark.parametrize(
    "status,created,removed",
    [
        ("exited", OLD, True),
        ("running", OLD, False),
        ("exited", NOW, False),
        ("exited", "invalid", False),
    ],
)
def test_stopped_container_retention_and_independent_inventory(
    tmp_path, status, created, removed
):
    final = replay(
        tmp_path,
        inventory(containers={"def": container(created=created, status=status)}),
    )
    assert final["removed_containers"] == (["def"] if removed else []), final
    assert final["removed"] == ([IMAGE] if removed else []), final


@pytest.mark.parametrize(
    "info",
    [
        {},
        {"version": {"Version": "5.6.2"}},
        {
            "version": {"Version": "5.6.2", "APIVersion": "5.6.2"},
            "host": {"serviceIsRemote": "false"},
        },
        {"ServerVersion": "26.0.0"},
    ],
)
def test_invalid_engine_identity_fails_closed(tmp_path, info):
    final = replay(tmp_path, inventory(info=info))
    assert final["removed"] == [], final
    assert not any(cmd[0] in {"ps", "images"} for cmd in final["trace"]), final


@pytest.mark.parametrize("racing", [False, True])
def test_successful_child_removal_preserves_fresh_dangling_parent(tmp_path, racing):
    state = inventory(new_reference=racing, protected_parent=PARENT)
    state["images"][PARENT] = {"Id": PARENT, "Created": NOW, "RepoTags": []}
    state["enumeration_ids"].append("sha256:" + PARENT)
    final = replay(tmp_path, state)
    assert final["removed"] == ([] if racing else [IMAGE]), final
    assert PARENT in final["images"] and final["removed_containers"] == [], final


@pytest.mark.parametrize("retention", ["2h", "5124095576030431h"])
def test_owner_reentry_preserves_context_and_scope(tmp_path, retention):
    final = replay(tmp_path, inventory(), owner=True, retention=retention)
    if retention != "2h":
        assert final["removed"] == final["removed_containers"] == [], final
    args = final["owner_reentry"]
    assert args[:3] == ["-u", "runner", "--"]
    for token in [
        "env",
        "-u",
        "CONTAINER_HOST",
        "CONTAINER_CONNECTION",
        "HOME=/disposable/runner",
        "XDG_RUNTIME_DIR=/run/user/1234",
        "RUNNER_GC_PODMAN_ONLY=1",
        f"RUNNER_GC_RETENTION={retention}",
        "RUNNER_GC_KEEP_TAG_PREFIX=keep/",
    ]:
        assert token in args


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("field", ["inspect", "reference"])
@pytest.mark.parametrize("suffix", ["\n", "\x00"])
def test_image_metadata_identity_rejects_control_suffix(
    tmp_path, platform, field, suffix
):
    state = inventory()
    if field == "inspect":
        state["images"][IMAGE]["Id"] = IMAGE + suffix
    else:
        state["containers"]["def"] = container(reference=PARENT + suffix)
    assert run_platform(platform, tmp_path, state)["removed"] == []


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("field", ["enumeration", "inspect"])
def test_different_full_image_identity_fails_closed(tmp_path, platform, field):
    state = inventory()
    if field == "enumeration":
        state["enumeration_ids"] = ["sha256:" + PARENT]
    else:
        state["images"][IMAGE]["Id"] = PARENT
    assert run_platform(platform, tmp_path, state)["removed"] == []


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("reference", [PARENT, "sha256:" + PARENT])
def test_other_native_reference_allows_positive_collection(
    tmp_path, platform, reference
):
    state = inventory(containers={"def": container(reference=reference)})
    final = run_platform(platform, tmp_path, state)
    assert final["removed"] == [IMAGE] and final["removed_containers"] == [], final


def test_model_and_real_retention_and_guards_lockstep():
    shell = (ROOT / "scripts/runner_gc.sh").read_text(encoding="utf-8")
    ps = (ROOT / "scripts/runner_gc_win.ps1").read_text(encoding="utf-8")
    model = (ROOT / "scripts/spec/podman_image_gc.qnt").read_text(encoding="utf-8")
    assert 'RETENTION="${RUNNER_GC_RETENTION:-2h}"' in shell
    assert "else { '2h' }" in ps
    assert "RETENTION_SECONDS = 7200" in model
    assert int("2") * 3600 == 7200
    assert '"$created" -ge "$PODMAN_CUTOFF"' in shell
    assert "$created -ge $Cutoff" in ps
    assert "ageSeconds > RETENTION_SECONDS" in model
    assert "podman rmi --no-prune" in shell
    assert "@('rmi', '--no-prune', $imageId)" in ps
    assert "ParentProtection = parentExists" in model
    assert "ReferenceProtection = referenced implies imageExists" in model
    assert (
        "ConfigurationProtection = not(configurationOk) implies not(removed)" in model
    )
    assert "check_age(witness)" in FAKE and "2**63 - 1" in FAKE


def test_powershell_runtime_required_when_selected():
    if os.environ.get("PODMAN_GC_REQUIRE_PWSH") == "1":
        assert PWSH is not None, (
            "selected mandatory PowerShell fake-I/O acceptance needs pwsh"
        )


@pytest.mark.skipif(
    PWSH is None,
    reason="PowerShell runtime absent; PS real-script replay unverified here",
)
@pytest.mark.parametrize(
    "scenario",
    [
        "ordinary",
        "keep",
        "late_keep",
        "new_reference",
        "metadata_error",
        "dry",
        "legacy_skip",
        "timeout",
        "foreign",
        "own",
        "custom_keep",
        "late_invalid",
        "object_inspect",
        "image_enumeration_error",
        "client_old",
        "server_old",
        "container",
        "clock_error",
        "invalid_clock",
        "negative_clock",
    ],
)
def test_powershell_public_gc_replay(tmp_path, scenario):
    state = inventory()
    if scenario == "keep":
        state["images"][IMAGE]["RepoTags"] = [
            "normal:latest",
            "localhost/keep/model:latest",
        ]
    if scenario == "metadata_error":
        state["images"][IMAGE]["RepoTags"] = None
    if scenario in {
        "late_keep",
        "new_reference",
        "late_invalid",
        "object_inspect",
        "image_enumeration_error",
        "clock_error",
    }:
        state[scenario] = True
    if scenario == "invalid_clock":
        state["ps_clock"] = "invalid"
    if scenario == "negative_clock":
        state["ps_clock"] = "1969-12-31T23:59:59Z"
    if scenario == "client_old":
        state["client"] = "4.9.0"
    if scenario == "server_old":
        state["server"] = "4.9.0"
    if scenario == "custom_keep":
        state["images"][IMAGE]["RepoTags"] = [
            "ordinary:latest",
            "registry.example/archive/model:latest",
        ]
    if scenario == "container":
        state["containers"]["def"] = container(status="exited")
    final = replay_powershell(
        tmp_path,
        state,
        dry=scenario == "dry",
        legacy_skip=scenario == "legacy_skip",
        timeout=scenario == "timeout",
        busy="own" if scenario == "own" else scenario == "foreign",
        prefix="registry.example/archive/" if scenario == "custom_keep" else "keep/",
    )
    assert final["removed"] == (
        [IMAGE] if scenario in {"ordinary", "own", "container"} else []
    ), final
    if scenario == "container":
        assert final["removed_containers"] == ["def"], final
    if scenario == "timeout":
        assert (tmp_path / "killed").read_text(encoding="utf-8") == "/PID 12345 /T /F"


@pytest.mark.parametrize(
    "created,deleted",
    [
        ("2029-12-31T21:59:59Z", True),
        ("2029-12-31T22:00:00Z", False),
        ("2029-12-31T22:00:01Z", False),
    ],
)
@pytest.mark.parametrize("platform", ["shell", "powershell"])
def test_real_script_two_hour_boundary(tmp_path, created, deleted, platform):
    state = inventory(containers={"def": container(created=created, status="exited")})
    state["images"][IMAGE]["Created"] = created
    final = run_platform(platform, tmp_path, state)
    assert final["removed"] == ([IMAGE] if deleted else []), final
    assert final["removed_containers"] == (["def"] if deleted else []), final


def test_tag_decoder_failure_after_schema_validation_retains_image(tmp_path):
    state = inventory()
    state["images"][IMAGE]["RepoTags"] = ["localhost/keep/model:latest"]
    assert replay(tmp_path, state, jq_fail=True)["removed"] == []


def test_own_worker_ancestor_is_not_a_foreign_job(tmp_path):
    assert replay(tmp_path, inventory(), busy="own")["removed"] == [IMAGE]


@pytest.mark.parametrize("platform", ["shell", "powershell"])
def test_seeded_real_script_replay(tmp_path, platform):
    if platform == "powershell" and PWSH is None:
        pytest.skip("PowerShell runtime absent; seeded PS replay unverified here")
    seeds = (
        [int(os.environ["PODMAN_GC_SEED"])]
        if "PODMAN_GC_SEED" in os.environ
        else range(32)
    )
    for seed in seeds:
        rng = random.Random(seed)
        fault = rng.choice(
            [
                "none",
                "late_keep",
                "late_invalid",
                "new_reference",
                "inspect_error",
                "container_enumeration_error",
            ]
        )
        keep, fresh = rng.choice([False, True]), rng.choice([False, True])
        state = inventory(**{fault: True}, seed=seed)
        state["enumeration_ids"] = [
            ("sha256:" if rng.choice([False, True]) else "") + IMAGE
        ]
        state["images"][IMAGE]["Id"] = (
            "sha256:" if rng.choice([False, True]) else ""
        ) + IMAGE
        if keep:
            state["images"][IMAGE]["RepoTags"] = [
                "normal:latest",
                "localhost/keep/model:latest",
            ]
        if fresh:
            state["images"][IMAGE]["Created"] = NOW
        final = run_platform(platform, tmp_path / str(seed), state)
        assert final["removed"] == (
            [] if keep or fresh or fault != "none" else [IMAGE]
        ), {"seed": seed, "trace": final["trace"], "state": final}


def test_powershell_override_must_name_an_executable(tmp_path):
    for override in (str(tmp_path / "missing"), str(tmp_path), ""):
        with pytest.raises(RuntimeError, match="PODMAN_GC_TEST_PWSH"):
            resolve_pwsh({"PODMAN_GC_TEST_PWSH": override})


def test_powershell_override_replaces_path_discovery():
    chosen = resolve_pwsh({"PODMAN_GC_TEST_PWSH": sys.executable})
    assert chosen is not None and Path(chosen).samefile(sys.executable)
    assert resolve_pwsh({}, which=lambda name: f"/found/{name}") == "/found/pwsh"


# Podman writes Created as Go's RFC 3339 time: nanoseconds, and Z or the
# engine's own offset. The age check must see that string, offset included.
@pytest.mark.parametrize(
    "created,deleted",
    [
        ("2020-01-01T09:00:00+09:00", True),
        ("2020-01-01T00:00:00.123456789Z", True),
        ("2029-12-31T23:59:59+02:00", True),  # 21:59:59Z
        ("2029-12-31T21:59:59-01:00", False),  # 22:59:59Z: not two hours old
    ],
)
def test_powershell_ages_created_as_the_wire_string(tmp_path, created, deleted):
    state = inventory(containers={"def": container(created=created, status="exited")})
    state["images"][IMAGE]["Created"] = created
    final = run_platform("powershell", tmp_path, state)
    assert final["removed"] == ([IMAGE] if deleted else []), final
    assert final["removed_containers"] == (["def"] if deleted else []), final


@pytest.mark.parametrize("platform", ["shell", "powershell"])
@pytest.mark.parametrize("created", [1577836800, None, {"Time": OLD}])
def test_non_string_created_is_kept(tmp_path, platform, created):
    state = inventory()
    state["images"][IMAGE]["Created"] = created
    assert run_platform(platform, tmp_path / "image", state)["removed"] == []
    state = inventory(containers={"def": container(created=created, status="exited")})
    final = run_platform(platform, tmp_path / "container", state)
    assert final["removed"] == [] and final["removed_containers"] == [], final


def _function_body(script, name):
    match = re.search(
        rf"^function {re.escape(name)} {{\n(.*?)^}}\n", script, re.MULTILINE | re.DOTALL
    )
    assert match is not None, name
    return match.group(1)


def test_get_podman_json_asks_the_real_cmdlet_for_date_kind():
    """PowerShell 7.5+ reads JSON date strings as strings, like 5.1 does; older
    ConvertFrom-Json has no DateKind and is called exactly as before."""
    script = (ROOT / "scripts/runner_gc_win.ps1").read_text(encoding="utf-8")
    body = _function_body(script, "Get-PodmanJson")
    # module-qualified: a function named Get-Command (the replay wrapper's)
    # cannot answer for the cmdlet
    assert (
        "$cmdlet = Microsoft.PowerShell.Core\\Get-Command -Name ConvertFrom-Json"
        " -CommandType Cmdlet -ErrorAction Stop\n" in body
    )
    assert (
        "if ($cmdlet.Parameters.ContainsKey('DateKind')) { $convert.DateKind = 'String' }"
        in body
    )
    assert "return Microsoft.PowerShell.Utility\\ConvertFrom-Json @convert" in body
    code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    # DateKind: only the capability test and the one use above
    assert sum(line.count("DateKind") for line in code) == 2
    assert "PSDefaultParameterValues" not in script
    calls = [line for line in code if "ConvertFrom-Json" in line]
    assert calls and all(line.strip() in body for line in calls), calls
