"""Unit tests for scripts/skills_readme_index.py (README blocks from frontmatter).

The skills README keeps its prose by hand; the blocks between the marker
comments are generated from each skill's frontmatter so they cannot drift:
the index (name, first sentence of the description, flags) and the credits
(derived skills with upstream repository, license, and what changed; the
skills whose origin is unconfirmed; the confirmed originals). A derived skill
that lacks the provenance contract is an error, never a blank cell.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from skills_readme_index import (
    MissingProvenanceError,
    SkillEntry,
    collect,
    main,
    render_credits,
    render_index,
    replace_between_markers,
)

DERIVED_MIT = (
    "license: MIT\nmetadata:\n  provenance: derived\n"
    "  upstream: owner/repo@abc1234:skills/beta\n  upstream-license: MIT\n  changes: trimmed\n"
)


def _skill(root: Path, name: str, frontmatter: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\n{frontmatter}---\n\n# {name}\n", encoding="utf-8"
    )


def test_collect_reads_first_sentence_flags_and_provenance(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "alpha",
        "name: alpha\ndescription: First sentence. Second sentence.\ndisable-model-invocation: true\n",
    )
    _skill(
        tmp_path,
        "beta",
        "name: beta\ndescription: 日本語の一文目。二文目。\n" + DERIVED_MIT,
    )
    entries = collect(tmp_path)
    assert [e.name for e in entries] == ["alpha", "beta"]
    alpha, beta = entries
    assert alpha == SkillEntry(
        name="alpha",
        summary="First sentence.",
        user_invoked=True,
        provenance="unknown",
        upstream=None,
        upstream_license=None,
        changes=None,
    )
    assert beta.summary == "日本語の一文目。"
    assert beta.provenance == "derived"
    assert beta.upstream == "owner/repo@abc1234:skills/beta"
    assert beta.upstream_license == "MIT"
    assert beta.changes == "trimmed"


def test_render_index_links_each_skill_and_marks_flags(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "alpha",
        "name: alpha\ndescription: Does A.\ndisable-model-invocation: true\n",
    )
    _skill(tmp_path, "beta", "name: beta\ndescription: Does B.\n" + DERIVED_MIT)
    table = render_index(collect(tmp_path))
    assert "| [`alpha`](alpha/SKILL.md) | Does A. | user-invoked |" in table
    assert "| [`beta`](beta/SKILL.md) | Does B. | fork of owner/repo |" in table


def test_render_credits_lists_the_three_provenance_states(tmp_path: Path) -> None:
    _skill(tmp_path, "beta", "name: beta\ndescription: Does B.\n" + DERIVED_MIT)
    _skill(
        tmp_path,
        "gamma",
        "name: gamma\ndescription: Does G.\nmetadata:\n  provenance: original\n",
    )
    _skill(tmp_path, "delta", "name: delta\ndescription: Does D.\n")
    out = render_credits(collect(tmp_path))
    assert "[owner/repo](https://github.com/owner/repo/tree/abc1234/skills/beta)" in out
    assert "| MIT | trimmed |" in out
    assert (
        "Origin not yet confirmed (no upstream found; confirm before publishing): `delta`"
        in out
    )
    assert "Original (confirmed): `gamma`" in out


def test_unknown_upstream_is_rendered_as_unknown(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "delta",
        "name: delta\ndescription: Does D.\nlicense: Apache-2.0\nmetadata:\n  provenance: derived\n"
        "  upstream: unknown\n  upstream-license: Apache-2.0\n  changes: origin not found\n",
    )
    assert "| unknown |" in render_credits(collect(tmp_path))


def test_derived_skill_without_contract_is_an_error(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "beta",
        "name: beta\ndescription: Does B.\nmetadata:\n  provenance: derived\n",
    )
    with pytest.raises(MissingProvenanceError, match="beta"):
        render_credits(collect(tmp_path))


def test_replace_between_markers_keeps_prose() -> None:
    doc = "intro\n<!-- skills-index:start -->\nold\n<!-- skills-index:end -->\noutro\n"
    out = replace_between_markers(doc, "skills-index", "new")
    assert (
        out
        == "intro\n<!-- skills-index:start -->\nnew\n<!-- skills-index:end -->\noutro\n"
    )


def test_replace_between_markers_requires_both_markers() -> None:
    with pytest.raises(ValueError, match="skills-index"):
        replace_between_markers("no markers here\n", "skills-index", "new")


def test_main_writes_and_check_detects_drift(tmp_path: Path) -> None:
    _skill(tmp_path, "alpha", "name: alpha\ndescription: Does A.\n")
    readme = tmp_path / "README.md"
    readme.write_text(
        "# skills\n\n<!-- skills-index:start -->\n<!-- skills-index:end -->\n\n"
        "<!-- credits:start -->\n<!-- credits:end -->\n",
        encoding="utf-8",
    )
    args = ["--skills-dir", str(tmp_path), "--readme", str(readme)]
    assert main(args) == 0
    assert "[`alpha`](alpha/SKILL.md)" in readme.read_text(encoding="utf-8")
    assert main([*args, "--check"]) == 0
    _skill(tmp_path, "zeta", "name: zeta\ndescription: Does Z.\n")
    assert main([*args, "--check"]) == 1


def test_collect_reads_metadata_with_a_trailing_comment(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "beta",
        "name: beta\ndescription: Does B.\nmetadata: # provenance\n  provenance: original\n",
    )
    assert collect(tmp_path)[0].provenance == "original"
