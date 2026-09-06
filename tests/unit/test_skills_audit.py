"""Unit tests for scripts/skills_audit.py (skills submodule structural audit).

The audit is the mechanical half of the skills conventions: frontmatter shape,
link and anchor resolution across the skill tree, balanced code fences, no
emoji markers, no Japanese instruction text outside the allowed places, the
provenance contract (derived / original / unknown), and (optionally)
agent-home drift. Every rule is exercised with a minimal skill tree under
tmp_path.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from skills_audit import (
    Finding,
    audit_tree,
    check_consumers,
    main,
    split_fences,
)

FRONTMATTER = "---\nname: {name}\ndescription: {desc}\n{extra}---\n"
DERIVED = (
    "license: Apache-2.0\n"
    "metadata:\n"
    "  provenance: derived\n"
    "  upstream: owner/repo@abc1234:skills/fork\n"
    "  upstream-license: Apache-2.0\n"
    "  changes: switched install commands to bun\n"
)


def _skill(
    root: Path,
    name: str,
    body: str = "# Title\n\nPlain English body.\n",
    desc: str = "Does a thing. Use when the user asks for the thing.",
    extra: str = "",
    fm_name: str | None = None,
) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        FRONTMATTER.format(name=fm_name or name, desc=desc, extra=extra) + body,
        encoding="utf-8",
    )
    return d


def _kinds(findings: list[Finding]) -> set[str]:
    return {f.kind for f in findings}


def _messages(findings: list[Finding], kind: str) -> set[str]:
    return {f.message for f in findings if f.kind == kind}


def test_valid_skill_has_no_findings(tmp_path: Path) -> None:
    _skill(tmp_path, "good")
    assert audit_tree(tmp_path) == []


def test_name_must_match_directory(tmp_path: Path) -> None:
    _skill(tmp_path, "good", fm_name="other")
    assert "frontmatter" in _kinds(audit_tree(tmp_path))


def test_description_length_and_presence(tmp_path: Path) -> None:
    _skill(tmp_path, "long", desc="x" * 1025)
    _skill(tmp_path, "empty", desc='""')
    kinds = [f for f in audit_tree(tmp_path) if f.kind == "frontmatter"]
    assert {f.skill for f in kinds} == {"long", "empty"}


def test_relative_link_and_cross_file_anchor_resolution(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "linker",
        body=(
            "# Linker\n\n"
            "[ok](references/a.md#section-one) "
            "[bad-file](references/missing.md) "
            "[bad-anchor](references/a.md#nope) "
            "[self](#linker)\n"
        ),
    )
    ref = tmp_path / "linker" / "references"
    ref.mkdir()
    (ref / "a.md").write_text("# Section One\n", encoding="utf-8")
    assert _messages(audit_tree(tmp_path), "link") == {
        "anchor not found: references/a.md#nope",
        "file not found: references/missing.md",
    }


def test_placeholder_links_in_output_skeletons_are_allowed(tmp_path: Path) -> None:
    d = _skill(tmp_path, "tmpl")
    (d / "templates").mkdir()
    (d / "templates" / "report.md").write_text(
        "![shot](screenshots/issue-001.png) [adr](adr/NNNN-title.md)\n",
        encoding="utf-8",
    )
    assert "link" not in _kinds(audit_tree(tmp_path))


def test_code_fences_must_balance(tmp_path: Path) -> None:
    _skill(tmp_path, "fence", body="# F\n\n```bash\necho hi\n")
    assert "fence" in _kinds(audit_tree(tmp_path))


def test_nested_fences_with_longer_outer_fence_are_balanced(tmp_path: Path) -> None:
    body = "# N\n\n````text\nouter\n```bash\ninner\n```\n````\n"
    _skill(tmp_path, "nested", body=body)
    assert "fence" not in _kinds(audit_tree(tmp_path))


def test_split_fences_returns_only_prose() -> None:
    prose, balanced = split_fences("a\n```\ncode\n```\nb\n")
    assert prose == "a\nb"
    assert balanced


def test_emoji_markers_are_rejected(tmp_path: Path) -> None:
    _skill(tmp_path, "emoji", body="# E\n\n- ✅ pass\n- ⚠️ warn\n")
    assert "emoji" in _kinds(audit_tree(tmp_path))


def test_emoji_in_bundled_references_is_allowed_for_derived_skills(
    tmp_path: Path,
) -> None:
    d = _skill(tmp_path, "vendored", extra=DERIVED)
    (d / "LICENSE.txt").write_text("Apache License\n", encoding="utf-8")
    (d / "references").mkdir()
    (d / "references" / "gotchas.md").write_text(
        "| ✅ ok | ❌ bad |\n", encoding="utf-8"
    )
    assert "emoji" not in _kinds(audit_tree(tmp_path))
    skill_md = d / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n- ✅ still not allowed here\n",
        encoding="utf-8",
    )
    assert "emoji" in _kinds(audit_tree(tmp_path))


def test_japanese_outside_allowed_places_is_rejected(tmp_path: Path) -> None:
    _skill(tmp_path, "jp", body="# J\n\nこれは日本語の指示文。\n")
    assert "language" in _kinds(audit_tree(tmp_path))


@pytest.mark.parametrize(
    ("name", "relative", "body"),
    [
        ("japanese-tech-writing", "SKILL.md", "# 規範\n\n日本語で書く。\n"),
        ("tmpl", "templates/x.md", "雛形は日本語。\n"),
        ("asset", "assets/x.md", "出力物は日本語。\n"),
        ("mcp", "references/mcp-setup.md", "案内は日本語。\n"),
        ("fenced", "SKILL.md", "# F\n\n```\n日本語のメッセージ雛形\n```\n"),
        ("inline", "SKILL.md", "# I\n\nFill in the `## 決定（記入待ち）` section.\n"),
    ],
)
def test_japanese_allowed_in_exempt_places(
    tmp_path: Path, name: str, relative: str, body: str
) -> None:
    d = _skill(tmp_path, name)
    target = d / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if relative == "SKILL.md":
        target.write_text(
            FRONTMATTER.format(name=name, desc="Use when asked.", extra="") + body,
            encoding="utf-8",
        )
    else:
        target.write_text(body, encoding="utf-8")
    assert "language" not in _kinds(audit_tree(tmp_path))


def test_japanese_trigger_phrases_in_description_are_allowed(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "trig",
        desc='Use when the user mentions 決定記録 or says "法務レビュー".',
    )
    assert "language" not in _kinds(audit_tree(tmp_path))


def test_provenance_state_must_be_known(tmp_path: Path) -> None:
    _skill(tmp_path, "odd", extra="metadata:\n  provenance: forked\n")
    assert _messages(audit_tree(tmp_path), "provenance") == {
        "metadata.provenance must be one of ['derived', 'original', 'unknown']"
    }


def test_upstream_requires_derived_state(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "fork",
        extra="metadata:\n  upstream: owner/repo@abc1234:skills/fork\n",
    )
    assert _messages(audit_tree(tmp_path), "provenance") == {
        "metadata.upstream is only allowed with metadata.provenance: derived"
    }


def test_derived_skill_needs_full_provenance_contract(tmp_path: Path) -> None:
    _skill(tmp_path, "fork", extra="metadata:\n  provenance: derived\n")
    assert _messages(audit_tree(tmp_path), "provenance") == {
        "metadata.upstream is required for a derived skill",
        "metadata.upstream-license is required for a derived skill",
        "metadata.changes is required for a derived skill",
    }


def test_licensed_derived_skill_must_ship_license_file(tmp_path: Path) -> None:
    d = _skill(tmp_path, "fork", extra=DERIVED)
    assert "provenance" in _kinds(audit_tree(tmp_path))
    (d / "LICENSE.txt").write_text("Apache License\n", encoding="utf-8")
    assert "provenance" not in _kinds(audit_tree(tmp_path))


def test_original_and_unknown_need_nothing_else(tmp_path: Path) -> None:
    _skill(tmp_path, "mine", extra="metadata:\n  provenance: original\n")
    _skill(tmp_path, "maybe", extra="metadata:\n  provenance: unknown\n")
    _skill(tmp_path, "bare")
    assert "provenance" not in _kinds(audit_tree(tmp_path))


def test_broken_links_in_bundled_docs_are_allowed_for_derived_skills(
    tmp_path: Path,
) -> None:
    d = _skill(tmp_path, "vendored", extra=DERIVED)
    (d / "LICENSE.txt").write_text("Apache License\n", encoding="utf-8")
    (d / "references").mkdir()
    (d / "references" / "api.md").write_text(
        "[gone](missing.md#nope)\n", encoding="utf-8"
    )
    assert "link" not in _kinds(audit_tree(tmp_path))
    skill_md = d / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n[gone](references/missing.md)\n",
        encoding="utf-8",
    )
    assert "link" in _kinds(audit_tree(tmp_path))


def test_check_consumers_reports_missing_drift_and_dangling(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _skill(root, "a")
    _skill(root, "b")
    home = tmp_path / "home"
    (home / "skills").mkdir(parents=True)
    # a: byte-identical copy (plus a runtime __pycache__ that must be ignored)
    a_copy = home / "skills" / "a"
    a_copy.mkdir()
    (a_copy / "SKILL.md").write_bytes((root / "a" / "SKILL.md").read_bytes())
    (a_copy / "__pycache__").mkdir()
    # b: drifted copy
    b_copy = home / "skills" / "b"
    b_copy.mkdir()
    (b_copy / "SKILL.md").write_text("stale", encoding="utf-8")
    # dangling symlink
    os.symlink(home / "skills" / "gone-target", home / "skills" / "gone")
    findings = check_consumers(root, [home / "skills"])
    assert {(f.skill, f.kind) for f in findings} == {
        ("b", "drift"),
        ("gone", "dangling"),
    }


def test_main_exit_code_reflects_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tmp_path, "good")
    assert main(["--skills-dir", str(tmp_path)]) == 0
    _skill(tmp_path, "bad", body="# B\n\n```\n")
    assert main(["--skills-dir", str(tmp_path)]) == 1
    assert "bad" in capsys.readouterr().out


def test_bare_empty_description_is_a_finding(tmp_path: Path) -> None:
    _skill(tmp_path, "blank", desc="")
    assert "description is empty" in _messages(audit_tree(tmp_path), "frontmatter")


def test_comment_after_metadata_key_keeps_the_mapping(tmp_path: Path) -> None:
    _skill(
        tmp_path, "commented", extra="metadata: # provenance\n  provenance: derived\n"
    )
    # the nested block was read, so the derived contract is enforced
    assert "metadata.upstream is required for a derived skill" in _messages(
        audit_tree(tmp_path), "provenance"
    )


def test_unquoted_colon_in_a_value_is_invalid_yaml(tmp_path: Path) -> None:
    _skill(
        tmp_path, "colon", extra="metadata:\n  provenance: unknown\n  note: from a: b\n"
    )
    messages = _messages(audit_tree(tmp_path), "frontmatter")
    assert any(m.startswith("not valid YAML") for m in messages)
    _skill(
        tmp_path,
        "quoted",
        extra='metadata:\n  provenance: unknown\n  note: "from a: b"\n',
    )
    assert not [f for f in audit_tree(tmp_path) if f.skill == "quoted"]


def test_check_consumers_compares_content_not_size_and_mtime(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _skill(root, "a", body="# A\n\nbody 1\n")
    home = tmp_path / "home" / "skills"
    home.mkdir(parents=True)
    copy = home / "a"
    copy.mkdir()
    (copy / "SKILL.md").write_bytes(
        (root / "a" / "SKILL.md").read_bytes().replace(b"body 1", b"body 2")
    )
    stat = (root / "a" / "SKILL.md").stat()
    os.utime(copy / "SKILL.md", ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert {(f.skill, f.kind) for f in check_consumers(root, [home])} == {
        ("a", "drift")
    }


def test_check_consumers_reports_type_mismatch_and_missing_home(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    d = _skill(root, "a")
    (d / "references").mkdir()
    (d / "references" / "x.md").write_text("x\n", encoding="utf-8")
    home = tmp_path / "home" / "skills"
    (home / "a").mkdir(parents=True)
    (home / "a" / "SKILL.md").write_bytes((d / "SKILL.md").read_bytes())
    (home / "a" / "references").write_text("a file, not a directory", encoding="utf-8")
    absent = tmp_path / "nowhere" / "skills"
    assert {(f.skill, f.kind) for f in check_consumers(root, [home, absent])} == {
        ("a", "drift"),
        ("nowhere", "missing-home"),
    }
