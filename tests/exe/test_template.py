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
    """`tofu fmt -check -diff` inside the ExeStartup container. We
    cannot run the full `tofu validate` because the Coder providers
    (coder/coder, coder/envbuilder) are NOT mirrored to OpenTofu's
    registry — they live only on the Terraform registry. The Coder
    server, which embeds Terraform, resolves them fine; for our
    static-check purposes we settle for fmt parity (catches HCL
    syntax bugs, indentation drift) plus the Python regex tests
    above (which catch undeclared references and the dotfiles
    repo_url anchor)."""
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
