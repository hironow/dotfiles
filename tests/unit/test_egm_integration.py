"""EGM is a complete pinned plugin/package, not seven detached skills."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import install_pi_extensions as installer

ROOT = Path(__file__).resolve().parents[2]
# v0.1.1 names skill directories egm-<name> (v0.1.0 used egm_<name>).
DESIGN_DOC = "skills/egm-draft/references/design_doc.md"


def _egm_tag() -> str:
    """The EGM tag the Claude declaration pins; every other pin follows it."""
    claude = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )
    repo, _, tag = claude["marketplaces"]["egm"].partition("#")
    assert repo == "google/elephant-goldfish-model"
    assert tag
    return tag


def test_egm_is_declared_as_a_complete_pinned_bundle() -> None:
    claude = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )
    assert "egm@egm" in claude["plugins"]
    pi = json.loads(
        (ROOT / "dump/harness/pi-packages.json").read_text(encoding="utf-8")
    )
    assert f"git:github.com/google/elephant-goldfish-model@{_egm_tag()}" in pi
    skills = json.loads(
        (ROOT / "dump/harness/skill-lock.json").read_text(encoding="utf-8")
    )["skills"]
    assert not any(
        record["source"] == "google/elephant-goldfish-model" for record in skills
    )


def test_only_the_approved_duplicate_entry_points_are_retired() -> None:
    records = json.loads(
        (ROOT / "dump/harness/skill-lock.json").read_text(encoding="utf-8")
    )["skills"]
    sources = {record["installed_dir"]: record["source"] for record in records}
    assert "to-spec" not in sources
    assert sources["to-prd"] == "hironow/skills"
    assert sources["intent-handover-governance"] == "hironow/skills"
    plugin = ROOT / "plugins/grilling"
    assert not (plugin / "skills/handover").exists()
    assert (plugin / "skills/grit-grill/SKILL.md").is_file()
    manifest = json.loads(
        (plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    entry = next(p for p in marketplace["plugins"] if p["name"] == "grilling")
    assert entry["version"] == manifest["version"] == "0.3.0"


def test_egm_reaches_every_agent_through_deploy_not_a_special_recipe() -> None:
    # Claude Code and Pi read EGM from their declarations; Codex and
    # Antigravity get it from the deploy step that follows the Pi pin.
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "egm-install" not in justfile
    deploy = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
    for step in (
        "install_pi_extensions.py",
        "codex_agy_plugins.py",
        "claude_plugins.py",
    ):
        assert step in deploy
    assert "docs/agents/egm.md" in (ROOT / "ROOT_AGENTS.md").read_text(encoding="utf-8")


def test_pi_reviewer_profile_is_restricted_without_overriding_route() -> None:
    text = (ROOT / "config/pi/agents/egm-reviewer.md").read_text(encoding="utf-8")
    front = dict(
        line.split(":", 1)
        for line in text.split("---", 2)[1].splitlines()
        if ":" in line
    )
    assert set(front["tools"].strip().split(", ")) == {"read", "grep", "find", "ls"}
    assert front["extensions"].strip() == ""
    for key in ("inheritProjectContext", "inheritGlobalContext", "inheritSkills"):
        assert front[key].strip() == "false"
    assert front["systemPromptMode"].strip() == "replace"
    assert front["defaultContext"].strip() == "fresh"
    assert not {"model", "thinking", "memory", "allowNestedSubagents"} & front.keys()
    guide = (ROOT / "ROOT_AGENTS_docs_agents_egm.md").read_text(encoding="utf-8")
    for requirement in (
        "2.1.271",
        'options.context: "fresh"',
        "host-required",
        "actual child",
    ):
        assert requirement in guide


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


def test_every_egm_pin_names_the_same_tag() -> None:
    # `just agent-bump egm` rewrites the pins together, and Codex takes its
    # ref from EGM_SOURCE; one left behind would split the agents.
    assert installer.EGM_SOURCE == f"{installer.EGM_PACKAGE}@{_egm_tag()}"


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
