"""dotfiles follows its own frontend CI guide (docs/agents/frontend-ci.md, ADR-0079).

The guide has five rules. Each test below pins the part of this repo that
carries one of them, and the ways it could pass while checking nothing: a
category lowered to a warning, a rule turned off with no reason, a file no gate
reads, a `check` script that shadows the type checker, an install that runs
package scripts, a last job that is skipped instead of failed.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
OXLINT = ROOT / ".oxlintrc.json"
TSCONFIG = ROOT / "tsconfig.json"
PACKAGE = ROOT / "package.json"
WORKFLOW = ROOT / ".github" / "workflows" / "frontend-ci.yaml"

CATEGORIES = (
    "correctness",
    "suspicious",
    "pedantic",
    "perf",
    "style",
    "restriction",
    "nursery",
)
# Third-party bytes we must not edit; each has its own gate.
VENDORED = {
    "site/vendor/**": "tests/unit/test_site_vendor.py (SHA-256 of npm's bytes)",
    "config/pi/extensions/rtk.ts": "just js-build, and rtk's own corpus",
}
OWN_FILES = (
    "site/copy.js",
    "config/pi/extensions/jev-sonnet-fallback.ts",
    "tests/unit/jev_sonnet_fallback.test.ts",
)
DEV_DEPENDENCIES = {
    "@earendil-works/pi-coding-agent",
    "@types/bun",
    "oxlint",
    "oxlint-tsgolint",
}
JOBS = ("lint", "typecheck", "build", "test")
_JS = re.compile(r"\.(?:[cm]?[jt]s|[jt]sx)$")
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def _recipe(name: str) -> str:
    bodies = re.findall(
        rf"^{re.escape(name)}:[^\n]*\n((?:[ \t]+[^\n]*(?:\n|$))*)",
        JUSTFILE,
        re.MULTILINE,
    )
    assert len(bodies) == 1, f"missing or ambiguous recipe: {name}"
    return bodies[0]


def _oxlint_text() -> str:
    return OXLINT.read_text(encoding="utf-8")


def _oxlint() -> dict:
    """The config as data. Its comments are whole lines, so they strip cleanly."""
    return json.loads(_LINE_COMMENT.sub("", _oxlint_text()))


def _tracked_js() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return [path for path in out.split("\0") if _JS.search(path)]


def _is_vendored(path: str) -> bool:
    return any(
        path.startswith(pattern.removesuffix("**"))
        if pattern.endswith("**")
        else path == pattern
        for pattern in VENDORED
    )


# --- rule 2: oxlint, every rule that can be on ---------------------------------


def test_every_category_is_an_error() -> None:
    assert _oxlint()["categories"] == dict.fromkeys(CATEGORIES, "error")


def test_type_aware_rules_are_on() -> None:
    assert _oxlint()["options"]["typeAware"] is True


def test_the_default_plugins_stay_in_the_list() -> None:
    plugins = set(_oxlint()["plugins"])
    assert {"eslint", "typescript", "unicorn", "oxc"} <= plugins, plugins


def test_no_rule_is_lowered_to_a_warning() -> None:
    config = _oxlint()
    blocks = [config.get("rules", {})]
    blocks += [override.get("rules", {}) for override in config.get("overrides", [])]
    for rules in blocks:
        for name, setting in rules.items():
            level = setting[0] if isinstance(setting, list) else setting
            assert level in {"off", "error"}, (name, level)


def test_every_rule_that_is_off_has_a_reason_above_it() -> None:
    lines = _oxlint_text().splitlines()
    off = [n for n, line in enumerate(lines) if re.search(r'":\s*"off"', line)]
    assert off, "expected the opt-outs to be listed by name"
    for n in off:
        above = n - 1
        while re.search(r'":\s*"off"', lines[above]):
            above -= 1  # several rules can share one reason
        reason = lines[above].strip()
        assert reason.startswith("// "), lines[n].strip()
        assert len(reason) > len("// ") + 20, f"too short to be a reason: {reason}"


def test_only_vendored_bytes_are_ignored() -> None:
    assert sorted(_oxlint()["ignorePatterns"]) == sorted(VENDORED)


def test_every_tracked_js_file_is_linted_or_vendored() -> None:
    tracked = _tracked_js()
    own = sorted(path for path in tracked if not _is_vendored(path))
    assert own == sorted(OWN_FILES), own


def test_oxlint_is_handed_the_tracked_files_only() -> None:
    # With no paths, oxlint walks the disk. A checkout that has a submodule
    # checked out (gcloud/knowledge-catalog), or any untracked folder, then
    # fails on files that are not ours, while CI and a fresh worktree pass.
    # `git ls-files` lists a submodule as one entry, never the files inside it.
    lint = _recipe("js-lint").replace("{{ BUN }}x", "bunx")
    assert re.search(
        r"git ls-files -z -- \{\{ JS_TRACKED \}\} \| xargs -0 -r bunx --no-install oxlint\s*$",
        lint,
    ), lint
    # One list of extensions: JS_TRACKED is JS_FILES without the exclusion that
    # only makes sense inside site/.
    assert """JS_TRACKED := replace(JS_FILES, " ':!vendor/**'", "")""" in JUSTFILE
    (js_files,) = re.findall(r'^JS_FILES := "(.+)"$', JUSTFILE, re.MULTILINE)
    extensions = ("ts", "tsx", "js", "jsx", "mjs", "cjs", "mts", "cts")
    assert js_files.split() == [
        *(f"'*.{extension}'" for extension in extensions),
        "':!vendor/**'",
    ]


def test_oxlint_is_pinned_and_installed_without_scripts() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    assert package["private"] is True
    assert set(package["devDependencies"]) == DEV_DEPENDENCIES
    assert "dependencies" not in package
    for name, version in package["devDependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), (name, version)
    assert (ROOT / "bun.lock").is_file()
    install = _recipe("js-install")
    assert "--frozen-lockfile" in install
    assert "--ignore-scripts" in install
    bunfig = tomllib.loads((ROOT / "bunfig.toml").read_text(encoding="utf-8"))
    # Seven days in seconds: Dependabot's bun (1.4.2) rejects "7d".
    assert bunfig["install"]["minimumReleaseAge"] == 604800
    assert bunfig["install"]["exact"] is True


# --- rule 1: bun check, never shadowed ------------------------------------------


def test_the_type_check_cannot_be_shadowed_by_a_script() -> None:
    assert "check --no-script" in _recipe("js-typecheck")
    for line in JUSTFILE.splitlines():
        runs_the_checker = re.search(r"(?:\bbun|BUN \}\}) check\b", line)
        if runs_the_checker and not line.lstrip().startswith(("#", "@echo")):
            assert "--no-script" in line, line
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    assert "check" not in package.get("scripts", {})


def test_the_type_check_reads_every_own_file_and_no_vendored_one() -> None:
    config = json.loads(TSCONFIG.read_text(encoding="utf-8"))
    options = config["compilerOptions"]
    assert options["strict"] is True
    assert options["noEmit"] is True
    # JS is only checked where a file opts in with `// @ts-check`, so the
    # vendored bundle that site/copy.js imports is loaded but not checked.
    assert options["allowJs"] is True
    assert options["checkJs"] is False
    assert sorted(config["include"]) == sorted(
        [
            "site/copy.js",
            "config/pi/extensions/jev-sonnet-fallback.ts",
            "tests/unit/*.test.ts",
        ]
    )
    first = (ROOT / "site" / "copy.js").read_text(encoding="utf-8").splitlines()[0]
    assert first == "// @ts-check"


def test_pi_types_never_reach_the_extension_at_run_time() -> None:
    # Pi places an extension as a symlink into this checkout, so a value import
    # would resolve to the dev dependency here instead of the running Pi
    # (ADR-0059). A type-only import is erased.
    for path in sorted((ROOT / "config" / "pi" / "extensions").glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for statement in re.findall(
            r"^import\b[^;]*?from\s+[\"'][^\"']+[\"']", text, re.MULTILINE | re.DOTALL
        ):
            if "@earendil-works/" in statement:
                assert statement.startswith("import type"), (path.name, statement)
    build = _recipe("js-build")
    assert "@earendil-works/" in build and "grep" in build, (
        "the build output is not searched"
    )


# --- rules 3 and 4: one shard, the whole suite ----------------------------------


def test_the_whole_suite_runs_in_one_shard() -> None:
    test = _recipe("js-test")
    assert "test ./tests/unit/" in test
    assert "--changed" not in test
    assert "--shard" not in test


# --- rule 5: parallel jobs behind one gate ---------------------------------------


def _job(name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", text, re.MULTILINE)
    assert match, f"no job {name}"
    return match.group(1)


def test_each_gate_is_its_own_job_running_one_recipe() -> None:
    for name in JOBS:
        job = _job(name)
        assert "needs:" not in job, name
        assert "github.event.pull_request.draft == false" in job, name
        assert "timeout-minutes:" in job, name
        assert f"just js-{name}" in job, name
        assert "DOTFILES_BUN: bun" in job, name


def test_the_last_job_fails_unless_every_job_passed() -> None:
    gate = _job("frontend")
    assert f"needs: [{', '.join(JOBS)}]" in gate
    assert "always()" in gate
    assert "github.event.pull_request.draft == false" in gate
    for name in JOBS:
        assert f"needs.{name}.result" in gate, name
    assert "success" in gate
    text = WORKFLOW.read_text(encoding="utf-8")
    jobs = re.findall(
        r"^  ([a-z][a-z0-9_-]*):\n", text.split("\njobs:\n", 1)[1], re.MULTILINE
    )
    assert sorted(jobs) == sorted([*JOBS, "frontend"]), jobs


def test_the_workflow_wakes_up_when_a_draft_becomes_ready() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "types: [opened, synchronize, reopened, ready_for_review]" in text
    assert "paths:" not in text, "a required check must always report"
    for uses in re.findall(r"uses: (\S+)", text):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", uses), uses


def test_the_local_gate_runs_the_same_recipes() -> None:
    for recipe in ("lint", "check"):
        body = _recipe(recipe)
        assert "just js-lint" in body, recipe
        assert "just js-typecheck" in body, recipe
        assert "just pi-jev-test" in body, recipe
    assert "vp -C site fmt --check" in _recipe("check")
    assert "vp -C site lint" not in JUSTFILE
    assert "vp -C site check" not in JUSTFILE
