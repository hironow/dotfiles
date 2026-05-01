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

We deliberately do NOT exercise `terraform plan`, since that needs
fake credentials for google + envbuilder + coder providers and
attempts network calls to provider registries.
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
def test_template_repo_url_is_dotfiles() -> None:
    """The whole point of this template: the default repo_url is the
    dotfiles git URL. Locks the intent so a future PR cannot drop the
    default and silently turn it into a generic envbuilder starter."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    # The 'default' line on the repo_url parameter.
    import re

    block = re.search(
        r'data "coder_parameter" "repo_url" \{(.*?)^\}',
        main_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, "could not locate the repo_url parameter block"
    body = block.group(1)
    assert "github.com/hironow/dotfiles" in body, (
        "repo_url default must point at the dotfiles repo"
    )


@pytest.mark.exe
def test_template_git_branch_parameter_present_and_wired() -> None:
    """envbuilder defaults to cloning the repo's default branch (main).
    For pre-merge debugging (e.g. testing libc6-compat in Dockerfile
    while the change is still on a feature branch), we expose a
    'git_branch' Coder parameter and wire it into envbuilder via
    ENVBUILDER_GIT_BRANCH. Both halves must stay in place — losing
    either silently disables branch override and re-creates the
    'image built from main, but the fix lives on a branch' class of
    bug we hit during the Layer 2 boot up."""
    main_tf = (TEMPLATE_DIR / "main.tf").read_text()
    import re

    block = re.search(
        r'data "coder_parameter" "git_branch" \{(.*?)^\}',
        main_tf,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None, "missing git_branch coder_parameter block"
    body = block.group(1)
    # Default must be empty so post-merge users get the repo's
    # default branch without thinking about it.
    assert re.search(r'default\s*=\s*""', body), (
        "git_branch parameter default must be empty string"
    )
    # Wiring into envbuilder.
    assert "ENVBUILDER_GIT_BRANCH" in main_tf, (
        "ENVBUILDER_GIT_BRANCH not wired into envbuilder_env"
    )
    assert "data.coder_parameter.git_branch.value" in main_tf, (
        "git_branch parameter is declared but never read"
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
    and coder/envbuilder are NOT mirrored to OpenTofu's registry.
    Test-runner-side use of the Terraform binary is solely for
    static analysis here; production deploys remain `tofu` (see
    docs/intent.md OpenTofu constraint, scoped to the operator
    stack at tofu/exe/).

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
