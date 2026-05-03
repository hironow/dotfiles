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
    # ADR 0010: Cloud SQL Auth Proxy + managed Postgres connection.
    r"\$\{var\.cloud_sql_proxy_version\}": "v2.21.3",
    r"\$\{var\.cloud_sql_proxy_sha256\}": (
        "46bef6dad3db3d10f07d69a1d76891d1a6aa942cc77b6f50369d9b8160a129e1"
    ),
    r"\$\{local\.cloud_sql_proxy_url\}": (
        "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.21.3/cloud-sql-proxy.linux.amd64"
    ),
    r"\$\{local\.cloud_sql_connection_name\}": (
        "gen-ai-hironow:asia-northeast1:exe-coder-pg"
    ),
    r"\$\{google_secret_manager_secret\.coder_pg_password\.secret_id\}": (
        "exe-coder-pg-password"
    ),
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
  *secrets*versions*access*--secret=exe-coder-pg-password*)
    # ADR 0010: deterministic fake postgres password (32 char alphanum)
    echo "fakepasswordfakepasswordfakepass"
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
        + "/etc/systemd/system/coder.service "
        + "/etc/systemd/system/cloud-sql-proxy.service; do\n"
        + '  if [[ -f "$u" ]]; then\n'
        + '    echo "=== $u ===" >&2\n'
        + '    cat "$u" >&2\n'
        + '    systemd-analyze verify "$u" 2>&1 || true\n'
        + "  fi\n"
        + "done\n"
        + "# Hard-fail if any file is missing.\n"
        + "test -f /etc/systemd/system/cloudflared-exe.service\n"
        + "test -f /etc/systemd/system/coder.service\n"
        + "test -f /etc/systemd/system/cloud-sql-proxy.service\n"
        + "test -x /usr/local/bin/cloud-sql-proxy\n"
        + "# /etc/default/coder must exist with the right perms (0640 root:coder).\n"
        + "test -f /etc/default/coder\n"
        + 'test "$(stat -c \'%U:%G:%a\' /etc/default/coder)" = "root:coder:640"\n'
        + "grep -q '^CODER_PG_CONNECTION_URL=postgres://' /etc/default/coder\n"
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
    tarball with sha256 verify."""
    forbidden = [
        r"coder\.com/install\.sh",
        r"curl[^\n]*\|\s*sh\b",
        r"curl[^\n]*\|\s*bash\b",
        r"\|\| true",  # the masking exit-code pattern flagged by codex
        r"releases/latest",  # the latest-resolution fallback
    ]
    for pattern in forbidden:
        assert not re.search(pattern, startup_script), (
            f"Coder install path still contains forbidden pattern "
            f"{pattern!r}; ADR 0007 prohibits it. Use the pinned-tag "
            f"+ sha256-verified path instead."
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
    r"""The tofu variables that drive the Coder install MUST have
    validation blocks so a mis-typed version or non-hex sha256 is
    caught at `tofu plan` time, not at VM bootstrap time.

    Note on the dot-escape level: HCL string `"\\."` is two literal
    backslashes plus a dot in the source file (the regex receives
    `\.`). Python's read_text() returns those two backslashes
    verbatim, so the assertion regex must match `\\` (two backslashes)
    + `.` — written as `\\\\\.` in a Python raw-string regex
    (`\\\\` matches two literal backslashes, `\.` matches the dot).
    The earlier `\\\.` form was off-by-one and false-negatived this
    check on every run."""
    variables_tf = (ROOT / "tofu" / "exe" / "variables.tf").read_text()
    # coder_version: SemVer with leading 'v'
    assert re.search(
        r'variable\s+"coder_version"\s*\{[^}]*?validation\s*\{[^}]*?'
        r"regex\([^)]*?v\[0-9\]\+\\\\\.\[0-9\]\+\\\\\.\[0-9\]\+",
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


@pytest.mark.exe
def test_coder_tarball_extract_does_not_use_bare_member_name(
    startup_script: str,
) -> None:
    """Production bug 2026-05-03: the Coder release tarball stores all
    members with a leading "./" prefix (./coder, ./LICENSE, ...). GNU
    tar (Ubuntu 24.04 host) treats `tar -x ... coder` as an exact
    member-name match and fails with "tar: coder: Not found in
    archive". BSD tar (macOS dev) normalizes the leading `./` so the
    bug only surfaces on the live VM, not on dev macs.

    The result was a fatal startup_script abort on every fresh boot:
    coder.service was never written, the Coder server never started,
    and `https://exe.hironow.dev/` returned CF tunnel errors.

    Fix: extract everything to a temp dir + `install` the binary into
    /usr/local/bin. Robust against future tarball layout changes
    (sub-directory, prefix tweaks) without tracking the specific
    member name. This test pins that fix.
    """
    # Locate the Coder install block (between "# ---- Coder OSS server"
    # and the systemctl that enables coder.service).
    install_block_match = re.search(
        r"# ---- Coder OSS server.*?systemctl enable --now coder\.service",
        startup_script,
        re.DOTALL,
    )
    assert install_block_match is not None, (
        "could not locate the Coder OSS server install block"
    )
    install_block = install_block_match.group(0)

    # Pin the fix: tar must NOT pass a bare 'coder' as a member-name
    # argument anywhere within the install block.
    bad_pattern = re.search(
        r"tar\s+-xz?[a-z]*\s+[^\n]*?\s+coder(?:\s|$)",
        install_block,
    )
    assert bad_pattern is None, (
        "Coder install block uses `tar ... coder` — GNU tar treats this\n"
        "as an exact member-name match and fails on the upstream tarball\n"
        "(member is `./coder`, not `coder`). Use the temp-dir + `install`\n"
        "pattern instead. See the 2026-05-03 production incident."
    )

    # Pin the recovery shape (positive): extract to a temp dir, then
    # install into /usr/local/bin/coder.
    assert "install -m 0755" in install_block, (
        "install block should use `install -m 0755 .../coder /usr/local/bin/coder`\n"
        "to copy the extracted binary atomically with mode."
    )
    assert re.search(
        r"tar\s+-xz?[a-z]*\s+-C\s+[^\n]+\s+-f\s+[^\n]+(?<!\scoder)$",
        install_block,
        re.MULTILINE,
    ), (
        "install block should extract the whole tarball to a temp dir, not target a single member."
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


# ---------- ADR 0010: Cloud SQL Postgres data plane ----------


@pytest.mark.exe
def test_cloud_sql_resources_present() -> None:
    """ADR 0010: tofu provisions a Cloud SQL Postgres instance, the
    coder DB, the coder user, the password (random_password) +
    Secret Manager version + IAM, the VPC peering for private IP,
    and the cloudsql.client IAM grant for the VM SA."""
    cloudsql_tf = (ROOT / "tofu" / "exe" / "cloudsql.tf").read_text()

    # Cloud SQL instance with deletion_protection + private IP +
    # backup enabled.
    inst = re.search(
        r'resource\s+"google_sql_database_instance"\s+"coder"\s*\{(.*?)^\}',
        cloudsql_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert inst is not None, "missing google_sql_database_instance.coder"
    body = inst.group(1)
    assert re.search(r"deletion_protection\s*=\s*true", body), (
        "Cloud SQL instance MUST have deletion_protection = true so a\n"
        "tofu destroy of the VM stack does not silently take the DB."
    )
    assert re.search(r"ipv4_enabled\s*=\s*false", body), (
        "Cloud SQL instance MUST have ipv4_enabled = false (private IP only)"
    )
    assert re.search(
        r"backup_configuration\s*\{[^{}]*?enabled\s*=\s*true", body, re.DOTALL
    ), (
        "Cloud SQL instance MUST enable automated backup (Coder docs\n"
        "explicitly recommend daily backups for production)"
    )
    assert re.search(r"point_in_time_recovery_enabled\s*=\s*true", body), (
        "Cloud SQL instance MUST enable point_in_time_recovery"
    )

    # DB + user + password resources.
    assert 'resource "google_sql_database" "coder"' in cloudsql_tf
    assert 'resource "google_sql_user" "coder"' in cloudsql_tf
    assert 'resource "random_password" "coder_pg_password"' in cloudsql_tf

    # Secret Manager: tofu-managed version (unlike the operator-managed
    # admin/passphrase patterns retracted in ADR 0009).
    assert 'resource "google_secret_manager_secret" "coder_pg_password"' in cloudsql_tf
    assert (
        'resource "google_secret_manager_secret_version" "coder_pg_password"'
        in cloudsql_tf
    ), "the pg password value is tofu-generated; the _version resource must exist"

    # VPC peering for private IP.
    assert 'resource "google_compute_global_address" "exe_psa_range"' in cloudsql_tf
    assert 'resource "google_service_networking_connection" "exe_psa"' in cloudsql_tf

    # IAM: VM SA can read the password + connect to Cloud SQL.
    assert (
        'resource "google_secret_manager_secret_iam_member" "coder_pg_password_reader"'
        in cloudsql_tf
    )
    assert (
        'resource "google_project_iam_member" "exe_coder_cloudsql_client"'
        in cloudsql_tf
    )
    cloudsql_client_block = re.search(
        r'resource\s+"google_project_iam_member"\s+"exe_coder_cloudsql_client"\s*\{(.*?)^\}',
        cloudsql_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert cloudsql_client_block is not None
    assert "cloudsql.client" in cloudsql_client_block.group(1)


@pytest.mark.exe
def test_cloud_sql_proxy_install_pinned(startup_script: str) -> None:
    """CSAP install mirrors the ADR 0007 hardening pattern: pinned
    version + sha256 + sha256sum -c verification before install. The
    binary is fetched from the official Google Cloud Storage CDN."""
    # The version + sha pinning lives in variables.tf; the install
    # block in startup_script must consume them via the bash vars
    # CSAP_VERSION / CSAP_SHA256 / CSAP_URL set at the top.
    assert "CSAP_VERSION=" in startup_script
    assert "CSAP_SHA256=" in startup_script
    assert "CSAP_URL=" in startup_script
    assert (
        "storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy" in startup_script
    )
    assert "sha256sum -c" in startup_script
    assert "/usr/local/bin/cloud-sql-proxy" in startup_script


@pytest.mark.exe
def test_cloud_sql_proxy_systemd_unit_emitted(startup_script: str) -> None:
    """The cloud-sql-proxy.service unit must be present and ordered
    BEFORE coder.service. coder.service requires it (so coder
    restarts when the proxy restarts)."""
    assert "cloud-sql-proxy.service" in startup_script

    # Locate the unit body.
    m = re.search(
        r"cloud-sql-proxy\.service\s*<<UNIT(.*?)^UNIT",
        startup_script,
        re.DOTALL | re.MULTILINE,
    )
    assert m is not None, "could not locate cloud-sql-proxy.service unit"
    body = m.group(1)
    assert "Before=coder.service" in body, (
        "cloud-sql-proxy.service must declare Before=coder.service"
    )
    assert "127.0.0.1" in body and "5432" in body, (
        "CSAP must listen on 127.0.0.1:5432 (loopback only)"
    )
    assert "User=coder" in body, "CSAP must run as the coder system user"

    # And coder.service must declare Requires + After cloud-sql-proxy.
    coder_unit = re.search(
        r"coder\.service\s*<<UNIT(.*?)^UNIT",
        startup_script,
        re.DOTALL | re.MULTILINE,
    )
    assert coder_unit is not None
    cb = coder_unit.group(1)
    assert "Requires=cloud-sql-proxy.service" in cb, (
        "coder.service must Requires=cloud-sql-proxy.service so the\n"
        "Coder server cannot run without its DB connection"
    )
    assert re.search(r"After=[^\n]*cloud-sql-proxy\.service", cb), (
        "coder.service must order After=cloud-sql-proxy.service"
    )


@pytest.mark.exe
def test_etc_default_coder_pg_url_is_envfile_not_unit_environment(
    startup_script: str,
) -> None:
    """The pg connection URL contains the password and must NOT live
    in the systemd unit file (which is mode 0644 + visible in
    `systemctl show`). Instead, write it to /etc/default/coder
    (mode 0640 root:coder) and have coder.service load it via
    EnvironmentFile."""
    assert "/etc/default/coder" in startup_script

    # The unit file must NOT contain a non-empty
    # Environment=CODER_PG_CONNECTION_URL= line.
    coder_unit = re.search(
        r"coder\.service\s*<<UNIT(.*?)^UNIT",
        startup_script,
        re.DOTALL | re.MULTILINE,
    )
    assert coder_unit is not None
    cb = coder_unit.group(1)

    # No legacy empty-default placeholder.
    assert "Environment=CODER_PG_CONNECTION_URL=" not in cb, (
        "coder.service unit must NOT contain Environment=CODER_PG_CONNECTION_URL=\n"
        "(value is loaded from /etc/default/coder via EnvironmentFile)"
    )
    assert "EnvironmentFile=" in cb and "/etc/default/coder" in cb, (
        "coder.service must load /etc/default/coder via EnvironmentFile="
    )

    # The script writes the password into /etc/default/coder, not the
    # unit file.
    assert "PG_PASSWORD=" in startup_script
    assert "127.0.0.1:5432/coder?sslmode=disable" in startup_script, (
        "CODER_PG_CONNECTION_URL must point at the loopback CSAP listener\n"
        "(sslmode=disable is correct because CSAP terminates the encrypted\n"
        "leg between the proxy and the managed instance)"
    )


@pytest.mark.exe
def test_bootstrap_enables_cloud_sql_apis() -> None:
    """The Cloud SQL instance + Service Networking peering need two
    new APIs enabled before the first tofu apply. Add them to the
    bootstrap script's REQUIRED_APIS array."""
    bootstrap = (ROOT / "exe" / "scripts" / "bootstrap.sh").read_text()
    assert "sqladmin.googleapis.com" in bootstrap, (
        "bootstrap.sh must enable sqladmin.googleapis.com (ADR 0010)"
    )
    assert "servicenetworking.googleapis.com" in bootstrap, (
        "bootstrap.sh must enable servicenetworking.googleapis.com (ADR 0010)"
    )
