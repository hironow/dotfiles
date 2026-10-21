"""Exercise the real root task against an isolated RTTM source tree."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def test_root_typecheck_resolves_dependencies_and_rejects_rttm_error(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[3]
    project = tmp_path / "tools/rttm"
    project.mkdir(parents=True)
    for relative in (
        "justfile",
        "pyproject.toml",
        "tools/rttm/pyproject.toml",
        "tools/rttm/uv.lock",
    ):
        shutil.copy2(root / relative, tmp_path / relative)
    (project / "tests").mkdir()
    (project / "visualize.py").write_text(
        "from matplotlib.colors import ListedColormap\ncolors = ListedColormap(['red'])\n",
        encoding="utf-8",
    )
    source = project / "to_eaf.py"
    source.write_text("import pympi\nprobe: int = 1\n", encoding="utf-8")
    uv = shutil.which("uv")
    just = shutil.which("just")
    assert uv is not None and just is not None
    env = os.environ.copy()
    # Use the already-synchronized RTTM environment: no installation or network.
    env["UV_PROJECT_ENVIRONMENT"] = sys.prefix
    env["UV_NO_SYNC"] = "1"
    env.pop("VIRTUAL_ENV", None)
    runner = f"{shlex.quote(uv.replace(chr(92), '/'))} run --frozen"
    command = [just, "--set", "UV_RUN", runner, "rttm-typecheck"]
    good = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    source.write_text("import pympi\nprobe: int = 'not an integer'\n", encoding="utf-8")
    bad = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    output = bad.stdout + bad.stderr
    assert bad.returncode != 0, output
    assert "invalid-assignment" in output and "to_eaf.py" in output, output
