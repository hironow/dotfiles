"""EGM is a complete pinned plugin/package, not seven detached skills."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import install_pi_extensions as installer

ROOT = Path(__file__).resolve().parents[2]
# v0.1.1 names skill directories egm-<name> (v0.1.0 used egm_<name>).
DESIGN_DOC = "skills/egm-draft/references/design_doc.md"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bundle"
    root.mkdir()
    # Every file verify_egm requires, plus one file it does not require but a
    # skill reads at run time (the index-flag test hides it).
    paths = [*installer.egm_required_paths(), DESIGN_DOC]
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    _git(root, "init", "--quiet")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    monkeypatch.setattr(installer, "EGM_COMMIT", _git(root, "rev-parse", "HEAD"))
    return root


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_index_flags_cannot_hide_changed_or_missing_runtime_files(
    bundle: Path, flag: str
) -> None:
    relative = DESIGN_DOC
    target = bundle / relative
    _git(bundle, "update-index", flag, relative)
    if flag == "--assume-unchanged":
        target.write_text("hidden modification\n", encoding="utf-8")
    else:
        target.unlink()
    assert _git(bundle, "status", "--porcelain") == ""  # Guard the reproduction.
    with pytest.raises(RuntimeError, match="index state"):
        installer.verify_egm(bundle)


def test_a_complete_clean_pinned_bundle_is_accepted(bundle: Path) -> None:
    installer.verify_egm(bundle)


@pytest.mark.parametrize(
    "damage", ["wrong-ref", "modified", "missing", "untracked", "ignored"]
)
def test_wrong_or_extra_bundle_content_fails_without_cleanup(
    bundle: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    head = _git(bundle, "rev-parse", "HEAD")
    target = bundle / "skills/egm-draft/SKILL.md"
    if damage == "wrong-ref":
        monkeypatch.setattr(installer, "EGM_COMMIT", "0" * 40)
    elif damage == "modified":
        target.write_text("local edit\n", encoding="utf-8")
    elif damage == "missing":
        target.unlink()
    else:
        target = bundle / "skills/extra/SKILL.md"
        target.parent.mkdir()
        target.write_text("extra skill\n", encoding="utf-8")
        if damage == "ignored":
            (bundle / ".git/info/exclude").write_text(
                "skills/extra/\n", encoding="utf-8"
            )
    before = target.read_bytes() if target.exists() else None
    with pytest.raises(RuntimeError, match="incomplete|wrong revision|local changes"):
        installer.verify_egm(bundle)
    assert _git(bundle, "rev-parse", "HEAD") == head
    assert (target.read_bytes() if target.exists() else None) == before


def test_agent_bump_runs_the_go_tool_against_this_checkout() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    recipe = justfile.split("agent-bump *args:\n", 1)[1].split("\n\n", 1)[0]
    assert "go -C tools/agent-bump run . --root" in recipe
    assert "{{ args }}" in recipe


def test_the_required_layout_is_the_one_v0_1_1_ships() -> None:
    # Recorded from the v0.1.1 tree (commit dea7761) on 2026-11-12: the skill
    # directories use hyphens, and the TRIZ reviewer persona is new.
    paths = installer.egm_required_paths()
    skills = sorted(p for p in paths if p.startswith("skills/"))
    assert skills == [
        "skills/egm-bootstrap/SKILL.md",
        "skills/egm-brainstorm/SKILL.md",
        "skills/egm-draft/SKILL.md",
        "skills/egm-drift-report/SKILL.md",
        "skills/egm-resolve/SKILL.md",
        "skills/egm-review-loop/SKILL.md",
        "skills/egm-review/SKILL.md",
    ]
    assert "agents/inventive_catalyst.md" in paths
