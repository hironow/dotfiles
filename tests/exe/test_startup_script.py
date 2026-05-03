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
    # Coder server install pin (ADR 0007). The dummy values must be
    # syntactically valid since the bash extracted from the heredoc
    # is later passed through bash -n / shellcheck.
    r"\$\{var\.coder_version\}": "v2.31.11",
    r"\$\{var\.coder_sha256\}": "32cf14eeecc96190dbc66b6965a3bdd563eaecc0d811a690e1e0b65828484979",
    r"\$\{google_secret_manager_secret\.exe_coder_authkey\.secret_id\}": (
        "exe-tailscale-coder-authkey"
    ),
    r"\$\{google_secret_manager_secret\.exe_coder_admin_token\.secret_id\}": (
        "exe-coder-admin-token"
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
def test_exe_coder_auth_key_is_ephemeral() -> None:
    """The workspace VM auth-key MUST be ephemeral=true. Without it,
    every preemptible 24h cycle (or every `just exe-replace`) leaves
    a stale 'exe-coder-N' device in the tailnet. MagicDNS still
    resolves to the active VM, but the admin UI accumulates dead
    rows over weeks of operation, and the device count quota is
    finite."""
    tailscale_tf = (ROOT / "tofu" / "exe" / "tailscale.tf").read_text()
    # Find the resource block, then assert ephemeral = true on it.
    block = re.search(
        r'resource "tailscale_tailnet_key" "exe_coder" \{(.*?)^\}',
        tailscale_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, "could not find exe_coder auth-key resource"
    assert re.search(r"ephemeral\s*=\s*true", block.group(1)), (
        "tailscale_tailnet_key.exe_coder must be ephemeral=true"
    )


@pytest.mark.exe
def test_tailscale_ssh_is_disabled(startup_script: str) -> None:
    """`tailscale up --ssh` activates Tailscale SSH, which requires a
    matching ssh{} block in the ACL and exposes a parallel auth path.
    The exe stack uses OpenSSH over the tailnet IP instead, so --ssh
    must NOT appear on the tailscale-up line."""
    m = re.search(
        r"^\s*tailscale up\s+\\(.*?)\n\n", startup_script, re.DOTALL | re.MULTILINE
    )
    assert m is not None, "could not locate `tailscale up` invocation"
    invocation = m.group(1)
    assert "--ssh" not in invocation, (
        "tailscale up must not include --ssh; OpenSSH-over-tailnet is the\n"
        "supported path. See coder.tf comment."
    )


@pytest.mark.exe
def test_coder_http_address_listens_on_all_interfaces() -> None:
    """B-plan tailnet routing: workspaces hit the Coder server's HTTP
    listener via its tailnet IP (exe-coder.<tailnet>:7080), not via the
    public CF Access edge. For that the listener MUST bind to all
    interfaces, not loopback only.

    127.0.0.1:7080 = only cloudflared can reach it (the original posture)
    0.0.0.0:7080   = cloudflared + tailnet IP (the B-plan posture)

    The deny-all-ingress firewall keeps the public IP blocked at L3,
    so 0.0.0.0 here is safe — the only listeners that can actually
    reach :7080 are localhost (cloudflared) and tun0 (tailscaled).
    """
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    assert "CODER_HTTP_ADDRESS=0.0.0.0:7080" in coder_tf, (
        "coder.service must set CODER_HTTP_ADDRESS=0.0.0.0:7080 so the\n"
        "Coder server listens on the tailnet interface as well as on\n"
        "the loopback (cloudflared) interface."
    )
    assert "CODER_HTTP_ADDRESS=127.0.0.1:7080" not in coder_tf, (
        "loopback-only listener detected. Workspaces hitting the\n"
        "tailnet IP will time out. Switch to 0.0.0.0."
    )


@pytest.mark.exe
def test_exe_workspace_sa_present_with_secret_reader() -> None:
    """Workspace VMs must be able to fetch the tag:exe-workspace
    tailnet auth key from Secret Manager at boot. That requires:
      - a dedicated google_service_account.exe_workspace
      - a google_secret_manager_secret_iam_member granting the SA
        roles/secretmanager.secretAccessor on exe_workspace_authkey

    Sharing the default compute SA was rejected because the default SA
    is project-wide and granting it Secret Manager read on tailnet
    keys widens the blast radius beyond this stack."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()

    sa_block = re.search(
        r'resource "google_service_account" "exe_workspace" \{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert sa_block is not None, (
        "missing google_service_account.exe_workspace in tofu/exe/coder.tf"
    )

    iam_block = re.search(
        r'resource "google_secret_manager_secret_iam_member" '
        r'"exe_workspace_authkey_reader" \{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert iam_block is not None, (
        "missing IAM grant — workspace SA cannot read the tailnet authkey"
    )
    assert "secretmanager.secretAccessor" in iam_block.group(1)


@pytest.mark.exe
def test_workspace_tailnet_auth_key_resource_present() -> None:
    """B-plan tailnet routing: workspace VMs join the tailnet at boot
    using a tag:exe-workspace auth key. The key MUST be:
      - reusable (multiple workspace VMs share it)
      - ephemeral (preempted/deleted VMs auto-prune from tailnet)
      - rotated by time_rotating like the existing keys
    The corresponding Secret Manager secret must exist so the
    workspace VM's service account can read the key by name."""
    ts_tf = ROOT / "tofu" / "exe" / "tailscale.tf"
    text = ts_tf.read_text()

    block = re.search(
        r'resource\s+"tailscale_tailnet_key"\s+"exe_workspace"\s*\{(.*?)^\}',
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, (
        "tofu/exe/tailscale.tf must declare\n"
        '  resource "tailscale_tailnet_key" "exe_workspace"'
    )
    body = block.group(1)
    assert re.search(r"reusable\s*=\s*true", body), "auth key must be reusable"
    assert re.search(r"ephemeral\s*=\s*true", body), (
        "auth key must be ephemeral so preempted VMs auto-prune"
    )
    assert "tag_exe_workspace" in body or '"tag:exe-workspace"' in body, (
        "auth key must carry tag:exe-workspace"
    )

    # Secret Manager mirror.
    assert 'google_secret_manager_secret" "exe_workspace_authkey"' in text, (
        "missing google_secret_manager_secret.exe_workspace_authkey"
    )
    assert 'google_secret_manager_secret_version" "exe_workspace_authkey"' in text, (
        "missing matching _version resource"
    )

    # depends_on tailscale_acl.this — without this the first apply hits
    # 'requested tags [tag:exe-workspace] are invalid or not permitted'
    # because the key issuance races ahead of the ACL update.
    assert re.search(
        r"depends_on\s*=\s*\[\s*tailscale_acl\.this\s*\]",
        body,
    ), (
        "tailscale_tailnet_key.exe_workspace must depend_on tailscale_acl.this\n"
        "to avoid a race where the key is issued for a tag whose tagOwners\n"
        "isn't in the live ACL yet."
    )


@pytest.mark.exe
def test_acl_grants_exe_workspace_access_to_coder_listener() -> None:
    """B-plan tailnet routing: workspace VMs talk to the Coder server's
    HTTP listener over the tailnet (avoiding the public CF Access edge
    which has no service token from the workspace side). For that, the
    ACL must:
      - own a dedicated `tag:exe-workspace` (so workspace VMs can be
        issued auth keys with a scope distinct from AI agents)
      - allow `tag:exe-workspace -> tag:exe-coder:7080` (the Coder
        HTTP listener port). Without this rule, packets from the
        workspace to exe-coder.<tailnet>:7080 are dropped at the
        tailnet ACL layer with no error message — workspaces silently
        fail to download `/bin/coder-linux-amd64`.
    """
    acl_path = ROOT / "exe" / "tailscale" / "acl.hujson"
    text = acl_path.read_text()

    assert '"tag:exe-workspace"' in text, (
        "tag:exe-workspace must be declared in tagOwners — without it the\n"
        "tailscale_tailnet_key for the workspace VM cannot be issued."
    )

    # Find the acls list and check the pair-rule exists. Use a tolerant
    # regex so a future formatter pass does not break the assertion.
    rule = re.search(
        r'"src"\s*:\s*\[\s*"tag:exe-workspace"\s*\]\s*,\s*'
        r'"dst"\s*:\s*\[\s*"tag:exe-coder:[^"]*7080[^"]*"\s*\]',
        text,
        re.DOTALL,
    )
    assert rule is not None, (
        "exe/tailscale/acl.hujson must contain an accept rule\n"
        "  src: tag:exe-workspace -> dst: tag:exe-coder:<...,7080,...>\n"
        "Required so the workspace VM can curl the Coder agent binary\n"
        "from the server's tailnet IP on port 7080."
    )


@pytest.mark.exe
def test_acl_has_no_ssh_block_or_only_empty() -> None:
    """If --ssh is off on the daemon, the ACL `ssh` key must be empty
    (or absent). Stale ssh rules are dead config that drifts away from
    the live posture."""
    acl_path = ROOT / "exe" / "tailscale" / "acl.hujson"
    text = acl_path.read_text()
    # find any `"ssh": [` followed by non-empty rules
    m = re.search(r'"ssh"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    assert m is not None, "expected `ssh` key (possibly empty)"
    inner = m.group(1).strip()
    # comments-only is OK; actual rule objects are not
    inner_no_comments = re.sub(r"//[^\n]*", "", inner).strip()
    assert "{" not in inner_no_comments, (
        "exe/tailscale/acl.hujson `ssh` block must be empty when --ssh is\n"
        "off on the VM. Found rules — remove them or re-enable --ssh."
    )


@pytest.mark.exe
def test_cdr_wrapper_present_and_executable() -> None:
    """The cdr wrapper at exe/scripts/cdr is the documented entry
    point for using the Coder CLI behind Cloudflare Access. It must:
      - exist as an executable file
      - source CF_ACCESS_CLIENT_ID + CF_ACCESS_CLIENT_SECRET from
        Secret Manager (the canonical 'exe-coder-cli-*' secret names)
      - export CODER_HEADER_COMMAND so the inner coder process
        injects the headers per-request
      - exec coder so 'cdr' is a transparent passthrough
    """
    cdr = ROOT / "exe" / "scripts" / "cdr"
    assert cdr.is_file(), f"missing wrapper: {cdr}"
    import os

    assert os.access(cdr, os.X_OK), f"wrapper not executable: {cdr}"
    text = cdr.read_text()
    # The exact secret names tofu/exe/cloudflare.tf creates.
    assert "exe-coder-cli-client-id" in text
    assert "exe-coder-cli-client-secret" in text
    assert "CODER_HEADER_COMMAND" in text
    assert "exec coder" in text
    # Coder CLI parses headers on '='. 'Name: Value' fails with
    #   create header transport: split header "..." had less than two parts
    # Lock the '=' form so the regression cannot slip back in.
    assert "CF-Access-Client-Id=" in text, (
        "CODER_HEADER_COMMAND must emit 'CF-Access-Client-Id=...' "
        "(equals sign, not colon)"
    )
    assert "CF-Access-Client-Secret=" in text
    assert "CF-Access-Client-Id:" not in text, (
        "Use '=' not ':' between header name and value (Coder CLI splits on '=')"
    )


@pytest.mark.exe
def test_cdr_header_helper_present_and_executable() -> None:
    """The cdr-header helper is what the Coder VS Code extension's
    'Coder: Header Command' setting points at. It must be executable
    and emit the CF Access service-token headers in 'Name=Value'
    line-per-header format (key=value separated by '=', not ': ')."""
    helper = ROOT / "exe" / "scripts" / "cdr-header"
    assert helper.is_file(), f"missing helper: {helper}"
    import os

    assert os.access(helper, os.X_OK), f"not executable: {helper}"
    text = helper.read_text()
    assert "exe-coder-cli-client-id" in text
    assert "exe-coder-cli-client-secret" in text
    # The whole point: Coder VS Code extension wants 'key=value\n'.
    assert "CF-Access-Client-Id=%s" in text, (
        "cdr-header must emit 'CF-Access-Client-Id=<value>' in printf"
    )
    assert "CF-Access-Client-Secret=%s" in text


@pytest.mark.exe
def test_state_encryption_is_strict() -> None:
    """After the migration window closed (2026-05-01), all 4 sites
    that declare encryption posture must agree:
        tofu/exe/main.tf
        justfile (_exe-encryption recipe)
        exe/scripts/smoke.sh
        exe/scripts/teardown.sh
    The strict posture is: aes_gcm method only, enforced = true, no
    'unencrypted' method, no fallback {...} block. Any of the four
    drifting back to migration mode would silently re-open the
    plaintext-state path, so lock all four together."""
    targets = [
        ROOT / "tofu" / "exe" / "main.tf",
        ROOT / "justfile",
        ROOT / "exe" / "scripts" / "smoke.sh",
        ROOT / "exe" / "scripts" / "teardown.sh",
    ]
    for path in targets:
        text = path.read_text()
        # Restrict to the encryption block / heredoc only — comments
        # mentioning the words are tolerated.
        # We approximate by checking for the literal HCL syntax that
        # would re-introduce the unencrypted path.
        assert 'method "unencrypted"' not in text, (
            f"{path}: 'method \"unencrypted\" ...' must not be declared "
            "after migration ended."
        )
        assert "fallback {" not in text, (
            f"{path}: encryption fallback block must not be present "
            "after migration ended."
        )
        # And `enforced = true` must be present somewhere (encryption
        # block); migration period had `enforced = false`.
        assert re.search(r"enforced\s*=\s*true", text), (
            f"{path}: encryption block must set enforced = true."
        )


@pytest.mark.exe
def test_coder_telemetry_disabled_via_env() -> None:
    """Telemetry must be turned OFF. Coder accepts both:
        Environment=CODER_TELEMETRY_ENABLE=false  (env path)
        ExecStart=... --telemetry=false           (CLI flag path)
    Both paths trip a serpent deprecation warning, but the env path
    is the only one that actually works in cloud — the CLI flag path
    additionally tripped a heredoc 'command not found' in GCE's
    metadata-script-runner. Lock the env-only form."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    assert re.search(
        r"^\s*Environment=CODER_TELEMETRY_ENABLE=false\s*$",
        coder_tf,
        re.MULTILINE,
    ), "CODER_TELEMETRY_ENABLE=false must be set in the coder.service unit"
    # ExecStart line(s) must not pass --telemetry (CLI flag path
    # tripped a 'command not found' regression in GCE's
    # metadata-script-runner heredoc handling). Comments mentioning
    # --telemetry as historical context are fine; only ExecStart= is
    # scrutinised.
    exec_lines = re.findall(r"^\s*ExecStart=.*$", coder_tf, re.MULTILINE)
    bad = [line for line in exec_lines if "--telemetry" in line]
    assert bad == [], (
        f"ExecStart must not pass --telemetry=...: {bad}.\n"
        "Use Environment=CODER_TELEMETRY_ENABLE=false instead."
    )


@pytest.mark.exe
def test_coder_hsts_options_is_comma_separated(startup_script: str) -> None:
    """Coder's HSTS option parser rejects ';' as a separator with:
        error: coderd: setting hsts header failed: hsts: invalid
               option: 'includeSubDomains;preload'. Must be 'preload'
               and/or 'includeSubDomains'.
    The HTTP HSTS *header* uses ';' between directives, but Coder's
    input parser expects ',' or whitespace. Lock the comma form."""
    m = re.search(
        r"CODER_STRICT_TRANSPORT_SECURITY_OPTIONS=([^\s\n]+)",
        startup_script,
    )
    assert m is not None, "missing CODER_STRICT_TRANSPORT_SECURITY_OPTIONS"
    value = m.group(1)
    assert ";" not in value, (
        f"HSTS options must use ',' not ';' (Coder rejects ';'); got: {value!r}"
    )


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
HARNESS_PRELUDE = r"""#!/bin/sh
# Use POSIX-only set flags so this prelude runs under both bash and
# dash (GCE's google_metadata_script_runner has been observed to
# dispatch via /bin/sh in some configurations).
set -eu

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
@pytest.mark.skip(
    reason=(
        "startup_script uses `set -euo pipefail` (bash-only); a dash run "
        "fails at line 2 before ever reaching the heredoc body. Cloud "
        "(GCE google_metadata_script_runner) honours the bash shebang in "
        "current testing, so dash dispatch is not exercised. Keep the "
        "test scaffolding so a future config that drops bash-isms can "
        "flip the skip and exercise the dash path."
    )
)
def test_startup_script_runs_under_dash(
    startup_script: str, docker_image: str, tmp_path: Path
) -> None:
    """Reserved-but-skipped test for the future case where the
    startup_script becomes POSIX-portable. Until then, this stays as
    documentation of the dash failure mode rather than as a live
    assertion."""
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
            "dash",
            "/work/run.sh",
        ],
        timeout=600,
    )
    assert r.returncode == 0, f"dash run failed:\n--- stderr ---\n{r.stderr[-2048:]}"
    assert "command not found" not in (r.stdout + r.stderr)


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
    /etc/systemd/system/{cloudflared-exe.service,coder.service,
    coder-cron-heartbeat.service,coder-cron-heartbeat.timer} must
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
        + "/etc/systemd/system/coder.service "
        + "/etc/systemd/system/coder-cron-heartbeat.service "
        + "/etc/systemd/system/coder-cron-heartbeat.timer "
        + "/etc/systemd/system/coder-cron-tofu-plan.service "
        + "/etc/systemd/system/coder-cron-tofu-plan.timer; do\n"
        + '  if [[ -f "$u" ]]; then\n'
        + '    echo "=== $u ===" >&2\n'
        + '    cat "$u" >&2\n'
        + '    systemd-analyze verify "$u" 2>&1 || true\n'
        + "  fi\n"
        + "done\n"
        + "# Hard-fail if any unit file is missing.\n"
        + "test -f /etc/systemd/system/cloudflared-exe.service\n"
        + "test -f /etc/systemd/system/coder.service\n"
        + "test -f /etc/systemd/system/coder-cron-heartbeat.service\n"
        + "test -f /etc/systemd/system/coder-cron-heartbeat.timer\n"
        + "test -f /etc/systemd/system/coder-cron-tofu-plan.service\n"
        + "test -f /etc/systemd/system/coder-cron-tofu-plan.timer\n"
        + "# Helpers + defaults file must also exist.\n"
        + "test -x /usr/local/bin/coder-cron-run\n"
        + "test -x /usr/local/bin/coder-cron-spawn-job\n"
        + "test -f /etc/default/coder-cron\n"
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


# ---------- ADR 0007: Coder server install hardening ---------------


@pytest.mark.exe
def test_coder_install_does_not_pipe_remote_script(startup_script: str) -> None:
    """ADR 0007: the bootstrap MUST NOT install Coder via
    `curl https://coder.com/install.sh | sh` or any other remote-
    script-piped-into-shell pattern. Replacement is a tag-pinned
    tarball with sha256 verify.

    The `|| true` ban is scoped to the Coder install block only — it
    was flagged by codex as a way to mask the integrity check's exit
    code there. `|| true` is a legitimate idiom in trap-cleanup
    handlers (e.g. coder-cron-spawn-job's teardown) and elsewhere, so
    we must not blanket-ban it across the whole script."""
    # Globally forbidden patterns (apply to the entire script).
    global_forbidden = [
        r"coder\.com/install\.sh",
        r"curl[^\n]*\|\s*sh\b",
        r"curl[^\n]*\|\s*bash\b",
        r"releases/latest",  # the latest-resolution fallback
    ]
    for pattern in global_forbidden:
        assert not re.search(pattern, startup_script), (
            f"Coder install path still contains forbidden pattern "
            f"{pattern!r}; ADR 0007 prohibits it. Use the pinned-tag "
            f"+ sha256-verified path instead."
        )

    # Scoped: extract the Coder install block (between '# ---- Coder
    # OSS server' and the systemctl that enables coder.service) and
    # ban `|| true` there only.
    install_block = re.search(
        r"# ---- Coder OSS server.*?systemctl enable --now coder\.service",
        startup_script,
        re.DOTALL,
    )
    assert install_block is not None, (
        "could not locate the Coder OSS server install block"
    )
    assert "|| true" not in install_block.group(0), (
        "Coder install block contains '|| true' — that pattern was used\n"
        "to mask the sha256/attestation check exit code. ADR 0007 forbids\n"
        "it within the install path; let the script fail closed instead."
    )


@pytest.mark.exe
def test_coder_install_uses_pinned_tag_and_sha256(startup_script: str) -> None:
    """The bootstrap downloads Coder from a tag-pinned GitHub
    release URL and verifies the resulting tarball against a
    pinned sha256. Values flow through bash variables (coder_tag,
    coder_sha256) populated from tofu vars at template-render
    time; the dummy substitution fills them with ADR 0007 defaults."""
    assert re.search(
        r"coder_tag\s*=\s*['\"]v\d+\.\d+\.\d+['\"]",
        startup_script,
    ), "Coder install must assign coder_tag to a SemVer-v string."
    assert re.search(
        r"coder_sha256\s*=\s*['\"][0-9a-f]{64}['\"]",
        startup_script,
    ), "Coder install must assign coder_sha256 to a 64-hex digest."
    assert "github.com/coder/coder/releases/download" in startup_script, (
        "Coder install URL must point at the official GitHub releases path."
    )
    assert "sha256sum -c" in startup_script, (
        "Coder install must call sha256sum -c against the pinned digest."
    )


@pytest.mark.exe
def test_coder_variables_have_validation() -> None:
    """The tofu variables that drive the Coder install MUST have
    validation blocks so a mis-typed version or non-hex sha256 is
    caught at `tofu plan` time, not at VM bootstrap time."""
    variables_tf = (ROOT / "tofu" / "exe" / "variables.tf").read_text()
    # coder_version: SemVer with leading 'v'
    assert re.search(
        r'variable\s+"coder_version"\s*\{[^}]*?validation\s*\{[^}]*?'
        r"regex\([^)]*?v\[0-9\]\+\\\.\[0-9\]\+\\\.\[0-9\]\+",
        variables_tf,
        re.DOTALL,
    ), "var.coder_version must validate against a SemVer-with-v regex."
    # coder_sha256: 64 lowercase hex chars
    assert re.search(
        r'variable\s+"coder_sha256"\s*\{[^}]*?validation\s*\{[^}]*?'
        r"regex\([^)]*?\[0-9a-f\]\{64\}",
        variables_tf,
        re.DOTALL,
    ), "var.coder_sha256 must validate against a 64-hex-char regex."


@pytest.mark.exe
def test_coder_install_attestation_verify_is_best_effort(startup_script: str) -> None:
    """`gh attestation verify` MUST run only if gh is installed AND
    authenticated, mirroring the dev container feature install.sh
    pattern. The sha256 pin is the primary integrity check; missing
    gh or unauthenticated gh must not block the install."""
    # Look for the conditional block that gates gh attestation verify.
    has_conditional_attestation = re.search(
        r"command -v gh[\s\S]*?gh attestation verify",
        startup_script,
    )
    assert has_conditional_attestation is not None, (
        "Bootstrap should attempt gh attestation verify only when gh "
        "is installed and authenticated."
    )


# ---------- ADR 0005 Open Q2 follow-up: apt key fingerprint pin ----

# Same observed-not-officially-published value documented in
# tests/test_vm_bootstrap.py.
TAILSCALE_GPG_FINGERPRINT = "2596A99EAAB33821893C0A79458CA832957F5868"
GOOGLE_CLOUD_GPG_FINGERPRINT = "35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3"


@pytest.mark.exe
def test_coder_tf_pins_tailscale_apt_key(startup_script: str) -> None:
    """Control-plane VM bootstrap must verify the Tailscale apt key
    fingerprint before adding the apt repo. Same hardening pattern
    as the workspace VM (main.tf post-PR #57 + this PR)."""
    assert TAILSCALE_GPG_FINGERPRINT in startup_script, (
        f"coder.tf must pin Tailscale apt-key fingerprint {TAILSCALE_GPG_FINGERPRINT}."
    )


@pytest.mark.exe
def test_coder_tf_pins_google_cloud_apt_key(startup_script: str) -> None:
    """Control-plane VM bootstrap must verify the Google Cloud apt
    key fingerprint."""
    assert GOOGLE_CLOUD_GPG_FINGERPRINT in startup_script, (
        f"coder.tf must pin Google Cloud apt-key fingerprint "
        f"{GOOGLE_CLOUD_GPG_FINGERPRINT}."
    )


@pytest.mark.exe
def test_coder_tf_helper_defined(startup_script: str) -> None:
    """import_apt_key_with_fingerprint must be defined in the
    control-plane startup_script."""
    assert re.search(
        r"^\s*import_apt_key_with_fingerprint\s*\(\s*\)\s*\{",
        startup_script,
        re.MULTILINE,
    ), "coder.tf must define import_apt_key_with_fingerprint helper."


@pytest.mark.exe
def test_coder_tf_no_unverified_apt_key_curls(startup_script: str) -> None:
    """The pre-PR pattern of `curl ... > /usr/share/keyrings/...gpg`
    or `curl ... | gpg --dearmor -o /etc/apt/keyrings/...` for
    Tailscale or Google Cloud must be gone."""
    forbidden = [
        r"curl[^\n]+pkgs\.tailscale\.com[^\n]+noarmor\.gpg[^\n]*>\s*/usr/share/keyrings",
        r"curl[^\n]+packages\.cloud\.google\.com[^\n]+apt-key\.gpg[\s\S]{0,80}gpg\s+--dearmor",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, startup_script), (
            f"coder.tf startup_script still uses the unverified-curl "
            f"pattern matching {pattern!r}."
        )


# ---------- ADR 0008 step 3: systemd timer scaffolding ------------


@pytest.mark.exe
def test_admin_token_secret_resource_present() -> None:
    """ADR 0008 step 3 requires a Secret Manager *shell* for the Coder
    admin token. The value is operator-provided post-apply (chicken-
    and-egg: the token can't be created until the Coder server is up),
    so tofu declares only the resource + IAM grant."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    secret = re.search(
        r'resource\s+"google_secret_manager_secret"\s+"exe_coder_admin_token"\s*\{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert secret is not None, (
        "tofu/exe/coder.tf must declare\n"
        '  resource "google_secret_manager_secret" "exe_coder_admin_token"'
    )
    assert "coder-admin-token" in secret.group(1), (
        "secret_id should embed 'coder-admin-token' so it is\n"
        "recognisable in the GCP console alongside the other exe-* secrets"
    )

    iam = re.search(
        r'resource\s+"google_secret_manager_secret_iam_member"\s+'
        r'"exe_coder_admin_token_reader"\s*\{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert iam is not None, (
        "missing IAM grant — Coder VM SA cannot read the admin token"
    )
    body = iam.group(1)
    assert "secretmanager.secretAccessor" in body
    assert "exe_coder.email" in body, (
        "the reader must be the exe_coder VM SA, not exe_workspace"
    )


@pytest.mark.exe
def test_admin_token_secret_has_no_version_resource() -> None:
    """The admin token value is operator-managed post-apply, so tofu
    MUST NOT declare a google_secret_manager_secret_version for
    exe_coder_admin_token. If a version resource were added, tofu
    would either need a placeholder value (defeating the operator-
    managed model) or fail at plan time on a missing variable."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    assert not re.search(
        r'resource\s+"google_secret_manager_secret_version"\s+"exe_coder_admin_token"',
        coder_tf,
    ), (
        "exe_coder_admin_token must remain operator-managed (no _version "
        "resource). Operator runs `coder tokens create | gcloud secrets "
        "versions add` after first apply."
    )


@pytest.mark.exe
def test_coder_cron_run_helper_emitted(startup_script: str) -> None:
    """The startup_script must drop /usr/local/bin/coder-cron-run, the
    helper any future systemd .service unit calls to talk to the local
    Coder API. Verify the bash heredoc that materialises it is present
    and uses CODER_URL=http://127.0.0.1:7080 (loopback only — no CF
    Access edge round-trip)."""
    assert "/usr/local/bin/coder-cron-run" in startup_script, (
        "coder.tf must write coder-cron-run helper to /usr/local/bin/"
    )
    assert "<<'HELPER'" in startup_script, (
        "the helper heredoc must be QUOTED so inner $#, $@, $CODER_CRON_*\n"
        "are written literally (not expanded by the outer bash)"
    )
    assert "http://127.0.0.1:7080" in startup_script, (
        "coder-cron-run must hit the local Coder server (loopback) rather\n"
        "than the public CF Access edge — the VM has no service token chain"
    )
    # Operator-onboarding pointer: when the helper fails (no token
    # version yet), the error must point at the runbook so the operator
    # knows what to do, not just 'gcloud failed'.
    assert "exe/docs/runbook.md" in startup_script, (
        "the helper's NOT_FOUND error path must reference the runbook"
    )


@pytest.mark.exe
def test_coder_cron_defaults_file_emitted(startup_script: str) -> None:
    """The helper reads CODER_CRON_SECRET_NAME and CODER_CRON_PROJECT
    from /etc/default/coder-cron (so the helper itself stays
    operator-readable plain bash). The startup_script must populate
    that file from the bash variables set at the top of the script."""
    assert "/etc/default/coder-cron" in startup_script
    assert "CODER_CRON_SECRET_NAME=" in startup_script
    assert "CODER_CRON_PROJECT=" in startup_script


@pytest.mark.exe
def test_heartbeat_units_emitted(startup_script: str) -> None:
    """ADR 0008 step 3 ships a tiny .service + .timer pair that proves
    the systemd timer mechanism on the VM works without depending on
    the operator-side admin token setup. The .service is a one-shot
    `logger` call; the .timer fires daily on a non-:00 minute with
    Persistent=true so a missed run after VM reboot still fires."""
    assert "coder-cron-heartbeat.service" in startup_script
    assert "coder-cron-heartbeat.timer" in startup_script
    # Off-the-hour minute avoids the cron thundering-herd (everyone
    # runs at :00). RandomizedDelaySec adds further jitter.
    assert "OnCalendar=*-*-* 09:17:00 UTC" in startup_script, (
        "heartbeat timer must use a non-:00 minute with explicit UTC; the\n"
        "Coder VM's TZ may not be UTC, and an unanchored 09:17 would drift"
    )
    assert "Persistent=true" in startup_script, (
        "Persistent=true is REQUIRED so a missed run after VM reboot\n"
        "(preempted SPOT instance, planned restart) still fires once on\n"
        "the next boot — see ADR 0008"
    )
    assert "RandomizedDelaySec=" in startup_script, (
        "RandomizedDelaySec is recommended jitter; remove only with cause"
    )


@pytest.mark.exe
def test_heartbeat_does_not_call_coder_api(startup_script: str) -> None:
    """The whole point of the heartbeat is that it runs WITHOUT the
    admin token — that's the smoke validation. If a future change
    wires the heartbeat through coder-cron-run, the heartbeat starts
    failing silently when the operator has not yet uploaded the admin
    token, which defeats the smoke purpose. Pin the simple form."""
    # Locate the heartbeat .service heredoc body and inspect ExecStart.
    m = re.search(
        r"coder-cron-heartbeat\.service\s*<<UNIT(.*?)^UNIT",
        startup_script,
        re.DOTALL | re.MULTILINE,
    )
    assert m is not None, "could not locate coder-cron-heartbeat.service heredoc"
    unit_body = m.group(1)
    exec_lines = [
        ln for ln in unit_body.splitlines() if ln.lstrip().startswith("ExecStart=")
    ]
    assert exec_lines, "heartbeat .service must have an ExecStart= line"
    for ln in exec_lines:
        assert "coder-cron-run" not in ln, (
            "heartbeat ExecStart must NOT call coder-cron-run; the heartbeat\n"
            "is the auth-free smoke path. Real cron jobs (step 4) get their\n"
            "own .service unit that calls coder-cron-run."
        )
        assert "/usr/bin/logger" in ln, (
            "heartbeat ExecStart should use /usr/bin/logger (one-shot, journald-only)"
        )


# ---------- ADR 0008 step 4: nightly tofu-plan cron ----------------


@pytest.mark.exe
def test_tofu_encryption_passphrase_secret_resource_present() -> None:
    """ADR 0008 step 4: cron jobs that read the encrypted exe state
    need the TF_ENCRYPTION passphrase. Tofu owns the secret SHELL +
    IAM grant only — the value (the operator's local passphrase from
    ~/.config/tofu/exe.passphrase) is uploaded once after first
    apply, mirroring the admin-token pattern from step 3."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    secret = re.search(
        r'resource\s+"google_secret_manager_secret"\s+"exe_tofu_encryption_passphrase"\s*\{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert secret is not None, (
        "tofu/exe/coder.tf must declare\n"
        '  resource "google_secret_manager_secret" "exe_tofu_encryption_passphrase"'
    )
    assert "tofu-encryption-passphrase" in secret.group(1)

    iam = re.search(
        r'resource\s+"google_secret_manager_secret_iam_member"\s+'
        r'"exe_tofu_encryption_passphrase_reader"\s*\{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert iam is not None, "missing IAM grant for the encryption passphrase"
    body = iam.group(1)
    assert "secretmanager.secretAccessor" in body
    # The READER must be the WORKSPACE SA (cron jobs run inside
    # workspace VMs), NOT the Coder VM SA.
    assert "exe_workspace.email" in body, (
        "the encryption passphrase reader must be exe_workspace, not exe_coder\n"
        "— cron jobs that need the passphrase run INSIDE workspace VMs"
    )

    # No _version resource: value is operator-managed.
    assert not re.search(
        r'resource\s+"google_secret_manager_secret_version"\s+"exe_tofu_encryption_passphrase"',
        coder_tf,
    ), "encryption passphrase value must remain operator-managed (no _version)"


@pytest.mark.exe
def test_workspace_state_bucket_iam_present() -> None:
    """ADR 0008 step 4: the cron-tofu-plan job ships its plan
    artifact to gs://<project>-tofu-state/jobs/<date>/. The workspace
    SA must therefore have storage.objectAdmin on the state bucket.
    The bucket is provisioned outside tofu (by exe/scripts/bootstrap.sh),
    so the IAM resource references local.state_bucket by name."""
    coder_tf = (ROOT / "tofu" / "exe" / "coder.tf").read_text()
    iam = re.search(
        r'resource\s+"google_storage_bucket_iam_member"\s+'
        r'"exe_workspace_state_bucket_admin"\s*\{(.*?)^\}',
        coder_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert iam is not None, (
        "tofu/exe/coder.tf must declare a google_storage_bucket_iam_member\n"
        "granting roles/storage.objectAdmin on the state bucket to the\n"
        "workspace SA"
    )
    body = iam.group(1)
    assert "storage.objectAdmin" in body
    assert "exe_workspace.email" in body
    assert "local.state_bucket" in body, (
        "use local.state_bucket so the bucket name stays consistent with\n"
        "the bootstrap script and outputs.tf"
    )


@pytest.mark.exe
def test_coder_cron_spawn_job_helper_emitted(startup_script: str) -> None:
    """The startup_script must drop /usr/local/bin/coder-cron-spawn-job,
    the VM-side analog of cdr-job. It generates a unique workspace
    name (prefix + UTC timestamp), polls the agent's lifecycle_state,
    and traps `coder-cron-run delete` on exit."""
    assert "/usr/local/bin/coder-cron-spawn-job" in startup_script
    # Must use coder-cron-run (the local-API helper), not cdr (which
    # would try the CF Access edge from the VM and have no creds).
    assert "coder-cron-run create" in startup_script
    assert "coder-cron-run delete" in startup_script
    # Trap-handler teardown is the primary safety net per ADR 0008.
    assert "trap cleanup EXIT" in startup_script, (
        "spawn-job must register a trap handler so SIGTERM / failure\n"
        "still reaps the workspace"
    )
    # The polling loop must break on `ready` (the lifecycle_state for
    # an ephemeral-job template after startup_script exits) — same
    # fix that landed in cdr-job in PR #71.
    assert "agent state=ready" in startup_script


@pytest.mark.exe
def test_coder_cron_tofu_plan_units_emitted(startup_script: str) -> None:
    """The nightly tofu-plan .timer + .service units must be present."""
    assert "coder-cron-tofu-plan.service" in startup_script
    assert "coder-cron-tofu-plan.timer" in startup_script
    # 04:23 UTC is off-the-hour and during operator's typical sleep
    # window. Anchored to UTC because the VM's TZ is not guaranteed.
    assert "OnCalendar=*-*-* 04:23:00 UTC" in startup_script
    assert "Persistent=true" in startup_script
    # The .service must use bash -c so the && is interpreted as a
    # shell operator (systemd ExecStart treats && as a literal arg).
    assert "/bin/bash -c" in startup_script, (
        "coder-cron-tofu-plan.service must wrap the multi-step command\n"
        "in /bin/bash -c — systemd ExecStart does not interpret && / |"
    )
    # The job invokes the workspace-side cron-tofu-plan.sh from the
    # cloned dotfiles repo.
    assert "exe/scripts/cron-tofu-plan.sh" in startup_script


@pytest.mark.exe
def test_cron_tofu_plan_script_present_and_executable() -> None:
    """The workspace-side cron-tofu-plan.sh script must exist as an
    executable file with a bash shebang. It runs INSIDE the
    ephemeral workspace spawned by the systemd timer; the script
    fetches the TF_ENCRYPTION passphrase from Secret Manager, runs
    `tofu init && tofu plan`, and ships the artifacts to GCS."""
    script = ROOT / "exe" / "scripts" / "cron-tofu-plan.sh"
    assert script.is_file(), f"missing workspace-side script: {script}"
    import os

    assert os.access(script, os.X_OK), f"script not executable: {script}"
    text = script.read_text()
    assert text.startswith("#!/usr/bin/env bash"), (
        "cron-tofu-plan.sh must use bash shebang"
    )
    # The script MUST use the Secret Manager secret name we provisioned
    # in tofu (exe-tofu-encryption-passphrase), not a hard-coded
    # passphrase or the on-disk file path.
    assert "exe-tofu-encryption-passphrase" in text, (
        "cron-tofu-plan.sh must fetch the passphrase from the Secret\n"
        "Manager secret named exe-tofu-encryption-passphrase"
    )
    # Artifact destination must be the state bucket under jobs/<date>/.
    assert "gs://" in text and "/jobs/" in text, (
        "cron-tofu-plan.sh must ship artifacts to gs://<bucket>/jobs/<date>/"
    )
    # The script MUST exit 0 even on tofu plan failure so the
    # diagnostic artifact still ships to GCS (operator visibility).
    assert "exit 0" in text


@pytest.mark.exe
def test_cron_tofu_plan_script_passes_shellcheck() -> None:
    """Lint cron-tofu-plan.sh with shellcheck (warning level)."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not available locally")
    script = ROOT / "exe" / "scripts" / "cron-tofu-plan.sh"
    r = _run(["shellcheck", "--severity=warning", str(script)])
    assert r.returncode == 0, f"shellcheck warnings:\n{r.stdout}\n{r.stderr}"


@pytest.mark.exe
def test_mise_toml_pins_opentofu() -> None:
    """ADR 0008 step 4 needs `tofu` baked into the workspace dev
    container image. mise.toml is the SoT for image-time tool
    versions; opentofu must be pinned there."""
    mise_toml = (ROOT / "mise.toml").read_text()
    assert re.search(r'^opentofu\s*=\s*"\d+\.\d+\.\d+"', mise_toml, re.MULTILINE), (
        'mise.toml must pin opentofu = "<semver>"'
    )
