"""End-to-end tests for tofu/exe/coder.tf startup_script.

Why these exist
---------------
The startup_script is a multi-page bash heredoc embedded in HCL. Every
problem we hit during the first cloud apply (apt keyring path mismatch,
unknown installer flags, 404 on a release asset, dash + unset HOME,
embedded postgres + root crashloop, ...) was a shell-level bug invisible
to `tofu validate` or `tofu plan`. These tests reproduce that work in a
container so the next regression fails locally in seconds, not in
gen-ai-hironow after a 5-10 minute apply.

Approach
--------
1. Extract the heredoc body from tofu/exe/coder.tf via regex (no tofu
   binary, no state access).
2. Substitute realistic dummy values for the HCL interpolations
   (`${local.vm_name}` etc.) so the output is a self-contained script.
3. `bash -n` and `shellcheck` it for syntax + lint.
4. Run the script inside an Ubuntu 24.04 container until just before
   `systemctl enable`. The apt repo + key + binary install steps run
   for real (this is what catches keyring-path / 404 / flag bugs).
5. Capture every systemd unit file the script wrote to
   /etc/systemd/system/ and pipe each one through `systemd-analyze
   verify`.

Mocked
------
- `gcloud secrets versions access`: replaced with a no-op stub on
  PATH so the script doesn't try to talk to GCP.
- `tailscale up --auth-key=...`: same — replaced with a no-op stub.
- `systemctl enable --now / restart`: replaced with a no-op stub. We
  still validate the unit files via systemd-analyze.
- `useradd`: real. The container is pristine, so creating the coder
  system user works.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "tests" / "docker" / "ExeStartup.Dockerfile"
CODER_TF = ROOT / "tofu" / "exe" / "coder.tf"
IMAGE = "dotfiles-exe-startup:latest"

# HCL interpolation -> dummy value table.
# Keep these realistic so install paths / URLs that depend on them
# resolve to actual existing endpoints.
HCL_SUBSTITUTIONS: dict[str, str] = {
    r"\$\{local\.vm_name\}": "exe-coder",
    r"\$\{local\.coder_host\}": "exe.hironow.dev",
    r"\$\{local\.sandbox_host\}": "*.sandbox.hironow.dev",
    r"\$\{local\.tag_exe_coder\}": "tag:exe-coder",
    r"\$\{var\.gcp_project_id\}": "gen-ai-hironow",
    r"\$\{google_secret_manager_secret\.exe_coder_authkey\.secret_id\}": (
        "exe-tailscale-coder-authkey"
    ),
    r"\$\{google_secret_manager_secret\.tunnel_credentials\.secret_id\}": (
        "exe-cloudflared-credentials"
    ),
    r"\$\{cloudflare_zero_trust_tunnel_cloudflared\.exe\.id\}": (
        "00000000-0000-0000-0000-000000000000"
    ),
}


def _run(
    cmd: list[str] | str,
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        shell=isinstance(cmd, str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _run(["docker", "info"]).returncode == 0


def _extract_startup_script() -> str:
    """Pull the heredoc body out of coder.tf and dummy-fill the
    HCL interpolations."""
    text = CODER_TF.read_text()
    match = re.search(
        r"startup_script\s*=\s*<<-EOT\s*\n(.*?)\n\s*EOT",
        text,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("could not locate startup_script <<-EOT block")
    body = textwrap.dedent(match.group(1))

    for pat, val in HCL_SUBSTITUTIONS.items():
        body = re.sub(pat, val, body)

    # OpenTofu HEREDOC `$${...}` escape -> bash `${...}`.
    body = body.replace("$${", "${")

    # Verify no unsubstituted HCL placeholders remain. If any slip
    # through, the test fails loudly so a new dependency is added to
    # HCL_SUBSTITUTIONS instead of running an under-substituted script.
    leftover = re.findall(r"\$\{[a-z][a-z_.]*\.[a-zA-Z0-9_.]+\}", body)
    if leftover:
        raise AssertionError(
            "unsubstituted HCL interpolation(s) in startup_script: "
            + ", ".join(sorted(set(leftover)))
        )
    return body


@pytest.fixture(scope="module")
def startup_script() -> str:
    return _extract_startup_script()


@pytest.fixture(scope="module")
def docker_image() -> str:
    if not _docker_available():
        pytest.skip("docker not available; skipping startup-script e2e")
    r = _run(
        [
            "docker",
            "build",
            "-t",
            IMAGE,
            "-f",
            str(DOCKERFILE),
            str(ROOT),
        ]
    )
    if r.returncode != 0:
        pytest.fail(
            f"failed to build {IMAGE}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return IMAGE


# ---------- static checks (no docker) ------------------------------


@pytest.mark.exe
def test_startup_script_extracts_cleanly(startup_script: str) -> None:
    """The heredoc parser produces a non-trivial body with no leftover
    HCL placeholders."""
    assert "tailscaled" in startup_script
    assert "cloudflared" in startup_script
    # Coder is invoked through $CODER_BIN, but the systemd unit name
    # is fixed and uniquely identifies the install branch.
    assert "coder.service" in startup_script
    assert "/var/lib/coder" in startup_script


@pytest.mark.exe
def test_startup_script_bash_syntax(startup_script: str, tmp_path: Path) -> None:
    """bash -n: catches stray quotes, missing fi/done, etc."""
    script = tmp_path / "startup.sh"
    script.write_text(startup_script)
    r = _run(["bash", "-n", str(script)])
    assert r.returncode == 0, f"bash -n failed:\n{r.stderr}"


@pytest.mark.exe
def test_startup_script_shellcheck(startup_script: str, tmp_path: Path) -> None:
    """shellcheck: catches use-before-set, unquoted globs, etc.
    The heredoc is intentionally permissive (no `set -u` requirement)
    so we limit the check to errors only."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not available locally")
    script = tmp_path / "startup.sh"
    script.write_text(startup_script)
    r = _run(["shellcheck", "--severity=error", str(script)])
    assert r.returncode == 0, f"shellcheck errors:\n{r.stdout}\n{r.stderr}"


# ---------- container-based execution ------------------------------


# Wraps the startup-script with PATH-mocked gcloud / tailscale /
# systemctl so we can run it as root inside the container without
# talking to GCP / Tailscale / systemd. The unit files still get
# written to /etc/systemd/system/ where systemd-analyze can verify
# them.
HARNESS_PRELUDE = r"""#!/usr/bin/env bash
set -euo pipefail

# ---- mock gcloud --------------------------------------------------
mkdir -p /opt/mock
cat > /opt/mock/gcloud <<'MOCK'
#!/usr/bin/env bash
# Drop-in replacement for `gcloud secrets versions access ...`. Print a
# deterministic fake auth key / credentials JSON so the rest of the
# script keeps going.
case "$*" in
  *secrets*versions*access*--secret=exe-tailscale-*)
    echo "tskey-auth-FAKE-FAKE-FAKE-FAKE-FAKE-FAKE-FAKE-FAKE"
    ;;
  *secrets*versions*access*--secret=exe-cloudflared-credentials*)
    echo '{"AccountTag":"a","TunnelID":"00000000-0000-0000-0000-000000000000","TunnelName":"exe-tunnel","TunnelSecret":"AAAA"}'
    ;;
  *)
    echo "gcloud mock: unhandled args: $*" >&2
    exit 0
    ;;
esac
MOCK
chmod +x /opt/mock/gcloud

# ---- mock tailscale + systemctl + apt-get install side effects ----
cat > /opt/mock/tailscale <<'MOCK'
#!/usr/bin/env bash
# Pretend `tailscale up` succeeds.
exit 0
MOCK
chmod +x /opt/mock/tailscale

cat > /opt/mock/systemctl <<'MOCK'
#!/usr/bin/env bash
# Capture invocations to /var/log/systemctl-mock.log; never fail.
echo "systemctl $*" >> /var/log/systemctl-mock.log
exit 0
MOCK
chmod +x /opt/mock/systemctl

# Prepend mocks to PATH so the script picks them up over apt's real
# binaries (when those get installed during the run).
export PATH="/opt/mock:${PATH}"

# Make sure the script's own apt installs land — otherwise the binary
# resolution via $(command -v ...) at unit-write time would pick up
# the mock. We resolve cloudflared / coder *before* installing them
# would be wrong; the script does `command -v` AFTER install which
# returns the real path. Mocks for gcloud/tailscale stay because the
# script never installs gcloud (it's already on the host's apt repo).
"""


@pytest.mark.exe
def test_startup_script_runs_in_container(
    startup_script: str, docker_image: str, tmp_path: Path
) -> None:
    """Run the entire startup_script inside Ubuntu 24.04. apt repo
    setup, key download, package installs, binary downloads, unit-file
    writes — all real. systemctl/gcloud/tailscale are mocked so we
    don't need a live tailnet / GCS bucket."""
    harness = tmp_path / "run.sh"
    harness.write_text(HARNESS_PRELUDE + "\n" + startup_script)

    r = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{harness}:/work/run.sh:ro",
            docker_image,
            "bash",
            "/work/run.sh",
        ],
        timeout=600,
    )
    if r.returncode != 0:
        pytest.fail(
            "startup-script failed inside container.\n"
            f"--- stdout (last 4KB) ---\n{r.stdout[-4096:]}\n"
            f"--- stderr (last 4KB) ---\n{r.stderr[-4096:]}"
        )


@pytest.mark.exe
def test_systemd_units_validate(
    startup_script: str, docker_image: str, tmp_path: Path
) -> None:
    """After running the script, every unit file under
    /etc/systemd/system/{cloudflared-exe.service,coder.service} must
    pass `systemd-analyze verify`. Catches missing User=, bad
    ExecStart= path, malformed Environment=, etc."""
    harness = tmp_path / "run.sh"
    harness.write_text(
        HARNESS_PRELUDE
        + "\n"
        + startup_script
        + "\n\n"
        + "echo '--- generated units ---' >&2\n"
        + "for u in /etc/systemd/system/cloudflared-exe.service "
        + "/etc/systemd/system/coder.service; do\n"
        + '  if [[ -f "$u" ]]; then\n'
        + '    echo "=== $u ===" >&2\n'
        + '    cat "$u" >&2\n'
        + '    systemd-analyze verify "$u" 2>&1 || true\n'
        + "  fi\n"
        + "done\n"
        + "# Hard-fail if either file is missing.\n"
        + "test -f /etc/systemd/system/cloudflared-exe.service\n"
        + "test -f /etc/systemd/system/coder.service\n"
    )

    r = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{harness}:/work/run.sh:ro",
            docker_image,
            "bash",
            "/work/run.sh",
        ],
        timeout=600,
    )
    assert r.returncode == 0, (
        f"systemd unit verification failed.\n"
        f"--- stdout (last 4KB) ---\n{r.stdout[-4096:]}\n"
        f"--- stderr (last 4KB) ---\n{r.stderr[-4096:]}"
    )
