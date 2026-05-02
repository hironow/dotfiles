"""End-to-end tests for the Coder workspace template at
exe/coder/templates/dotfiles-devcontainer/.

What runs and why
-----------------
The template is HCL evaluated by the *Coder server* (which embeds
Terraform), not by the operator. Even so, we can run
`terraform init -backend=false` + `terraform validate` against the
template directory in a clean container to catch:

  - Provider / resource type misspellings
  - Missing required arguments
  - Invalid HCL syntax
  - References to undeclared resources (e.g. the well-known
    'coder_agent.main' typo we patched out of upstream)

`terraform plan` runs in a sub-test for deeper checks (zone
propagation, parameter defaults, etc.); fake Google credentials
keep it offline.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "exe" / "coder" / "templates" / "dotfiles-devcontainer"
DOCKERFILE = ROOT / "tests" / "docker" / "ExeStartup.Dockerfile"

# Use the existing exe-startup container — adding terraform there is
# cheaper than maintaining a second image. We invoke terraform via
# 'apt install -y --no-install-recommends terraform' on entry; the
# image's apt cache from the build is still warm, so this finishes
# in ~30 s on first run and a few seconds on cache hits.


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return _run(["docker", "info"]).returncode == 0


@pytest.mark.exe
def test_template_main_tf_present() -> None:
    """The template directory exists and contains a main.tf."""
    assert TEMPLATE_DIR.is_dir(), f"missing template dir: {TEMPLATE_DIR}"
    assert (TEMPLATE_DIR / "main.tf").is_file()
    assert (TEMPLATE_DIR / "README.md").is_file()


@pytest.mark.exe
def test_template_image_default_points_to_artifact_registry() -> None:
    """The whole point of this template: workspaces pull a prebuilt
    dev container image from the stack's Artifact Registry repo,
    instead of running envbuilder per workspace. The default image
    string must reference asia-northeast1-docker.pkg.dev/gen-ai-hironow
    so a future PR cannot silently turn it into a generic starter
    pulling some other registry."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    block = re.search(
        r'variable "image" \{(.*?)^\}',
        main_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, 'missing variable "image" block'
    body = block.group(1)
    assert "asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles" in body, (
        "image variable default must reference the dotfiles Artifact "
        "Registry repo at asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles."
    )


@pytest.mark.exe
def test_template_no_envbuilder() -> None:
    """The envbuilder pattern was replaced by a prebuilt image on
    docs/adr/0002-coder-prebuilt-image.md. Lock the migration: no
    envbuilder provider, no envbuilder_cached_image resource, no
    ENVBUILDER_* env vars in the actual HCL (comments mentioning
    envbuilder by name in commit-message-style 'differences from
    upstream' notes are acceptable)."""
    raw = (TEMPLATE_DIR / "main.tf").read_text()
    # Strip line- and block-comments before grepping so historical
    # mentions in comment headers don't false-match.
    import re

    no_block_comments = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    code = "\n".join(
        line
        for line in no_block_comments.splitlines()
        if not line.lstrip().startswith("#")
    )
    forbidden_in_code = [
        # provider {} block referencing the envbuilder source
        'source = "coder/envbuilder"',
        # the cached_image resource the prior template used
        '"envbuilder_cached_image"',
        # any ENVBUILDER_* env var name
        "ENVBUILDER_",
    ]
    for needle in forbidden_in_code:
        assert needle not in code, (
            f"template still references {needle!r}; the envbuilder path "
            "was retired in favour of prebuilt-image pull. See "
            "docs/adr/0002-coder-prebuilt-image.md."
        )


@pytest.mark.exe
def test_template_startup_script_pulls_and_runs_image() -> None:
    """The new gcp-vm-container-style startup_script must:
      - configure docker auth against Artifact Registry
      - docker pull `var.image`
      - docker run with the agent init script as its command
    Without this chain the workspace VM would boot but the dev
    container would never start."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    m = re.search(
        r"startup_script\s*=\s*<<-META\s*\n(.*?)\n\s*META",
        main_tf,
        re.DOTALL,
    )
    assert m is not None, "could not locate startup_script <<-META block"
    body = m.group(1)
    assert "gcloud --quiet auth configure-docker" in body, (
        "startup_script must configure docker auth for Artifact Registry"
    )
    assert "docker pull" in body and "var.image" in body, (
        "startup_script must docker pull '${var.image}' before running it"
    )
    assert "docker run" in body, "startup_script must docker run the prebuilt image"
    assert "init_script" in body, (
        "startup_script must invoke the coder_agent init_script as the "
        "container command"
    )


@pytest.mark.exe
def test_template_provider_coder_has_internal_url_override() -> None:
    """B-plan tailnet routing: the workspace VM downloads the agent
    binary from `${ACCESS_URL}/bin/coder-linux-amd64`. ${ACCESS_URL}
    is rendered server-side by Coder from `metadata.GetCoderUrl()`,
    which prefers `provider "coder" { url = ... }` over the global
    CODER_ACCESS_URL. Setting `url` to the tailnet-internal URL
    routes the binary download through the tailnet, bypassing the
    public CF Access edge. Without this override, workspaces hit
    the public URL and fail OIDC.

    See coder/coder provisioner/terraform/provision.go provisionEnv()."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    block = re.search(r'provider "coder" \{(.*?)\}', main_tf, re.DOTALL)
    assert block is not None, 'missing provider "coder" block'
    body = block.group(1)
    assert re.search(r"url\s*=", body), (
        'provider "coder" block must set url = var.coder_internal_url\n'
        "(or equivalent) so workspace agent downloads bypass CF Access."
    )
    assert "coder_internal_url" in main_tf, (
        "template must declare a 'coder_internal_url' variable wired into "
        "the provider 'coder' url"
    )


@pytest.mark.exe
def test_template_workspace_sa_variable_present() -> None:
    """Workspace VMs need a SA that can read the tailnet authkey from
    Secret Manager. Hardcoding the SA email per-environment is brittle;
    the operator stack already exports it as `exe_workspace_sa_email`.
    The template MUST receive that value through a `workspace_sa_email`
    variable and apply it on `google_compute_instance.vm`."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    var_block = re.search(
        r'variable "workspace_sa_email" \{(.*?)^\}',
        main_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert var_block is not None, 'missing variable "workspace_sa_email"'

    # The VM must consume it.
    assert "var.workspace_sa_email" in main_tf, (
        "google_compute_instance.vm must use var.workspace_sa_email\n"
        "for its service_account.email — currently the template uses\n"
        "data.google_compute_default_service_account.default which has\n"
        "no Secret Manager Reader on the workspace authkey."
    )


@pytest.mark.exe
def test_template_startup_script_joins_tailnet() -> None:
    """The workspace VM's startup-script must:
    - install tailscaled (apt-get install tailscale)
    - fetch the tag:exe-workspace authkey from Secret Manager
    - bring the device up under tag:exe-workspace BEFORE the dev
      container starts. The container's CODER_AGENT_URL points at
      exe-coder over MagicDNS, which only resolves once the host is
      on the tailnet.
    """
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()

    # Look at the startup_script local — match the heredoc body.
    import re

    m = re.search(
        r"startup_script\s*=\s*<<-META\s*\n(.*?)\n\s*META",
        main_tf,
        re.DOTALL,
    )
    assert m is not None, "could not locate startup_script <<-META block"
    body = m.group(1)

    assert "tailscale" in body, "startup_script must install tailscale"
    assert "tailscale up" in body, "startup_script must run `tailscale up`"
    assert "tag:exe-workspace" in body or "tag_exe_workspace" in body, (
        "startup_script must advertise tag:exe-workspace"
    )
    assert "secrets versions access" in body, (
        "startup_script must fetch the auth-key from Secret Manager"
    )


@pytest.mark.exe
def test_template_agent_startup_skips_homebrew_and_add_update() -> None:
    """The agent startup_script runs `coder dotfiles -y URL`, which
    git-clones the dotfiles repo and execs install.sh. install.sh
    tries to install Homebrew and replay brew/gcloud bundle dumps —
    neither of which we want on a CI-style workspace.

    install.sh honours these env vars to skip those stages:
      INSTALL_SKIP_HOMEBREW=1   (skips Homebrew install)
      INSTALL_SKIP_ADD_UPDATE=1 (skips `just add-all` + `just update-all`)

    With both set, install.sh still runs `just clean` + `just deploy`
    (symlink ~/.zshrc, sheldon lock, fzf-tab clone, etc.) — the
    actually-useful part of dotfiles personalisation. Without them
    install.sh aborts at homebrew install with `set -eu` and the
    workspace never finishes personalising.

    INSTALL_SKIP_GCLOUD was previously needed because alpine couldn't
    run the glibc gcloud SDK installer; the debian-12 devcontainer
    base + the google-cloud-cli devcontainer feature now provide
    gcloud natively, so `command -v gcloud` short-circuits the
    install branch. The env var is no longer required and was
    removed."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    # Find the coder_agent.dev startup_script body.
    m = re.search(
        r'resource "coder_agent" "dev" \{(.*?)^\}',
        main_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert m is not None, "missing coder_agent.dev resource"
    body = m.group(1)

    for env_var in (
        "INSTALL_SKIP_HOMEBREW",
        "INSTALL_SKIP_ADD_UPDATE",
    ):
        assert f"export {env_var}=1" in body, (
            f"coder_agent.dev startup_script must `export {env_var}=1`\n"
            "before invoking `coder dotfiles`. Otherwise install.sh\n"
            "aborts at homebrew install on workspaces."
        )

    assert "INSTALL_SKIP_GCLOUD" not in body, (
        "INSTALL_SKIP_GCLOUD was removed — gcloud now arrives via the\n"
        "google-cloud-cli devcontainer feature on debian-12, so the\n"
        "install.sh gcloud branch no-ops via `command -v gcloud`. If\n"
        "this assertion fires, the env var was re-added; remove it.\n"
    )


@pytest.mark.exe
def test_template_does_not_use_code_server_module() -> None:
    """Upstream `registry.coder.com/coder/code-server/coder` ships a
    Linux x86_64 glibc binary; alpine + musl can sometimes load it
    via libc6-compat / gcompat but the install path the module uses
    (dropping the binary into ~/.local/bin and starting it on
    127.0.0.1:13337) frequently fails on the dotfiles devcontainer,
    producing 5-second-cadence 'connection refused on localhost:13337'
    spam in the agent logs.

    intent.md states the dev container is terminal-first ('cdr ssh
    my-first-ws.dev' is the documented entry point); the code-server
    browser UI is not part of the goal. Drop the module to silence
    the noise. A future PR can reintroduce a music-friendly browser
    IDE with a different module if the need arises.
    """
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    assert "code-server" not in main_tf, (
        "module.code-server has been removed from the template — see\n"
        "test docstring for the rationale. If you need a browser IDE,\n"
        "use a separate PR with a musl-compatible alternative."
    )


@pytest.mark.exe
def test_template_no_undeclared_agent_reference() -> None:
    """Upstream's gcp-devcontainer starter referenced a non-existent
    `coder_agent.main` from the code-server / jetbrains modules — the
    actual resource is `coder_agent.dev[0]` (count-bound). Locking
    against that copy/paste rot."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    declared = set(re.findall(r'resource\s+"coder_agent"\s+"(\w+)"', main_tf))
    referenced = set(re.findall(r"coder_agent\.(\w+)", main_tf))
    undeclared = referenced - declared
    assert undeclared == set(), (
        "coder_agent references with no matching resource: "
        + ", ".join(sorted(undeclared))
    )


@pytest.mark.exe
def test_template_tofu_fmt(tmp_path: Path) -> None:
    """`tofu fmt -check -diff` inside the ExeStartup container.
    Catches HCL syntax / indentation drift. Cheap, fast (provider
    download not needed). The deeper plan-time checks live in
    test_template_terraform_plan below."""
    if not _docker_available():
        pytest.skip("docker not available")

    r = _run(
        [
            "docker",
            "build",
            "-t",
            "dotfiles-exe-startup:latest",
            "-f",
            str(DOCKERFILE),
            str(ROOT),
        ]
    )
    assert r.returncode == 0, f"docker build failed:\n{r.stderr}"

    runner = """
set -eux
apt-get update -y >/dev/null
apt-get install -y --no-install-recommends curl ca-certificates jq tar >/dev/null
tag=$(curl -fsSL https://api.github.com/repos/opentofu/opentofu/releases/latest | jq -r .tag_name)
ver=${tag#v}
curl -fsSL -o /tmp/tofu.tar.gz \\
  "https://github.com/opentofu/opentofu/releases/download/${tag}/tofu_${ver}_linux_amd64.tar.gz"
tar -xz -C /usr/local/bin -f /tmp/tofu.tar.gz tofu
chmod 0755 /usr/local/bin/tofu
cd /work/template
tofu fmt -check -diff -recursive
"""

    r = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{TEMPLATE_DIR}:/work/template:ro",
            "dotfiles-exe-startup:latest",
            "bash",
            "-c",
            runner,
        ],
        timeout=300,
    )
    assert r.returncode == 0, (
        f"tofu fmt -check failed inside container:\n"
        f"--- stdout (last 2KB) ---\n{r.stdout[-2048:]}\n"
        f"--- stderr (last 2KB) ---\n{r.stderr[-2048:]}"
    )


@pytest.mark.exe
def test_template_terraform_plan(tmp_path: Path) -> None:
    """`terraform plan` against the template inside the ExeStartup
    container. This catches the class of bug the operator hit on
    'cdr templates push' that the static checks above missed:

        Error: expected a non-empty string
          on main.tf line 47, in provider 'google':
            zone = module.gcp_region.value
        zone was set to ``

    Provider initialisation, default-value propagation through
    coder_parameter / Coder modules, and resource-attribute
    requirements all surface here.

    Why Terraform (not OpenTofu): the Coder server embeds Terraform,
    so 'cdr templates push' uses Terraform's registry. coder/coder
    is NOT mirrored to OpenTofu's registry. Test-runner-side use of
    the Terraform binary is solely for static analysis here;
    production deploys remain `tofu` (see docs/intent.md OpenTofu
    constraint, scoped to the operator stack at tofu/exe/).

    Skipped if docker is unavailable."""
    if not _docker_available():
        pytest.skip("docker not available")

    # 'dotfiles-exe-startup:latest' from the previous test or its build.
    r = _run(
        [
            "docker",
            "build",
            "-t",
            "dotfiles-exe-startup:latest",
            "-f",
            str(DOCKERFILE),
            str(ROOT),
        ]
    )
    assert r.returncode == 0, f"docker build failed:\n{r.stderr}"

    # Pin a recent Terraform version. 1.9 is the last minor before
    # the BSL change matters in any way for distribution; for in-test
    # binary use the version pin is mostly about reproducibility.
    runner = """
set -eux
apt-get update -y >/dev/null
apt-get install -y --no-install-recommends curl ca-certificates unzip >/dev/null

TF_VERSION="1.9.8"
curl -fsSL -o /tmp/terraform.zip \\
  "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip"
unzip -o /tmp/terraform.zip -d /usr/local/bin/ >/dev/null
chmod 0755 /usr/local/bin/terraform

# Read-only mount; work in a writable copy.
cp -r /work/template /tmp/template
cd /tmp/template

terraform init -input=false -no-color

# The Coder providers reach out to a synthetic 'workspace owner' /
# 'workspace' identity during plan; the Coder docs call this the
# 'preview plan'. project_id is the only required input.
#
# -refresh=false avoids the data 'google_compute_default_service_account'
# block reaching out to GCP for live data — this test runs without
# any GCP credentials. If plan-time *resource* validation has a real
# bug (zone empty, malformed reference, undeclared resource), it
# still surfaces here even with refresh off.
#
# Inject fake Google credentials so the provider does not fail
# initialisation. The fake file is the minimum shape Terraform
# accepts for an authorized_user; it never gets used because we
# use -refresh=false.
mkdir -p /tmp/fake-gcp
cat > /tmp/fake-gcp/key.json <<'JSON'
{
  "type": "authorized_user",
  "client_id": "fake.apps.googleusercontent.com",
  "client_secret": "fake",
  "refresh_token": "fake"
}
JSON
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/fake-gcp/key.json
export GOOGLE_PROJECT=test-template-plan

terraform plan -input=false -no-color -refresh=false \\
  -var "project_id=test-template-plan" \\
  -var "workspace_sa_email=fake-workspace-sa@test-template-plan.iam.gserviceaccount.com" \\
  -out=/tmp/plan.bin

terraform show -no-color /tmp/plan.bin | head -40
"""

    r = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{TEMPLATE_DIR}:/work/template:ro",
            "dotfiles-exe-startup:latest",
            "bash",
            "-c",
            runner,
        ],
        timeout=600,
    )
    combined = r.stdout + "\n" + r.stderr

    # The whole point of this test is the class of bugs that show up
    # as 'expected a non-empty string' (or other provider-init parse
    # errors) BEFORE the plan can dispatch real GCP calls. If those
    # phrases appear, fail loudly — they meant the operator hit the
    # same regression that motivated this test.
    bad_phrases = [
        "expected a non-empty string",
        "Reference to undeclared resource",
        "Unsupported argument",
        "Invalid value for variable",
    ]
    for phrase in bad_phrases:
        if phrase in combined:
            pytest.fail(
                f"terraform plan surfaced a template-side bug: "
                f"'{phrase}' in output.\n"
                f"--- stdout (last 4KB) ---\n{r.stdout[-4096:]}\n"
                f"--- stderr (last 4KB) ---\n{r.stderr[-4096:]}"
            )

    # We expect the plan to fail at GCP-call time on the
    # 'data google_compute_default_service_account' read because the
    # test environment has no real GCP credentials. That is OK and
    # means we cleared all the static / provider-init checks we
    # actually want this test to police. Validate that we got at
    # least to the 'Plan:' summary OR that the first failure came
    # from data-source GCP I/O rather than HCL evaluation.
    assert (
        "Plan:" in combined
        or "Error when reading or editing GCE default service account" in combined
        or r.returncode == 0
    ), (
        "terraform plan never reached the GCP I/O phase — likely a "
        "static / provider-init issue not covered by 'bad_phrases'.\n"
        f"--- stdout (last 4KB) ---\n{r.stdout[-4096:]}\n"
        f"--- stderr (last 4KB) ---\n{r.stderr[-4096:]}"
    )
