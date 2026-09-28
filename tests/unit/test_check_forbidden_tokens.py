"""Unit tests for scripts/check_forbidden_tokens.py.

This repo is PUBLIC, and one work unit needs a private GCP project's
identifiers -- project id, project number, billing account id, org name --
to stay out of every tracked file, every commit message, every PR body and
every public Actions log. Prose discipline is not a control: the identifiers
appear naturally in `gcloud` output, in `tofu plan` output and in a bucket
path, so the wall has to be mechanical.

Two properties of that wall are what make it usable rather than theatre, and
they are what most of these tests pin:

1. **Added lines only.** Six tracked files and nine commit messages on `main`
   already contain the org token; cleaning those is a separate work unit. A
   whole-file scanner would therefore fail every commit forever and get
   switched off within the hour. So the staged scan reads the ADDED lines of
   the staged diff (plus the staged paths), never the files.
2. **The token list lives outside the repo.** `~/.config/dotfiles/forbidden-tokens`,
   mode 0600, is the only place the real strings exist -- putting them in a
   tracked config would publish exactly what the guard protects. A checkout
   with no list (CI, a fresh clone) therefore scans nothing and passes; these
   tests only ever use synthetic tokens.

The blob refusal is the one unconditional leg: `*.tfplan` / `*.tfstate*` /
`terraform.tfvars` / `backend.hcl` and anything git calls binary cannot be
scanned at all, so they are refused outright regardless of the token list.
Zero tracked files in this repo are binary by git's own definition, so that
refusal has no blast radius on existing content.

The tests drive real `git` repositories under `tmp_path` rather than mocking
subprocess: the whole point of the guard is what `git diff --cached` actually
emits for renames, new files, deletions and binary blobs, and a mock would
assert only that the author guessed that format right.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_forbidden_tokens.py"

# Synthetic only -- never the real strings the guard protects.
TOKEN_A = "zzsynthetictokenalpha"
TOKEN_B = "ZZ-Synthetic-Token-Beta"
TOKEN_NUM = "999888777666"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_forbidden_tokens", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


# --- helpers ----------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _init_repo(tmp_path: Path) -> Path:
    """A real git repo with one clean commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("clean baseline\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "chore: baseline")
    return repo


def _token_list(tmp_path: Path, *tokens: str, mode: int = 0o600) -> Path:
    path = tmp_path / "forbidden-tokens"
    body = "# synthetic list for tests\n\n" + "".join(f"{t}\n" for t in tokens)
    path.write_text(body)
    path.chmod(mode)
    return path


def _run(
    repo: Path,
    *args: str,
    token_list: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop(mod.TOKENS_ENV, None)
    env.pop(mod.ALLOW_BINARY_ENV, None)
    # An operator's real list must never leak into a test run.
    env["HOME"] = str(repo.parent / "home-not-there")
    env["XDG_CONFIG_HOME"] = str(repo.parent / "xdg-not-there")
    if token_list is not None:
        env[mod.TOKENS_ENV] = str(token_list)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def _stage(repo: Path, rel: str, content: str) -> None:
    """Stage a file, forcing past any ignore rule.

    `-f` is not a test convenience: the operator's global gitignore already
    covers `*.tfstate` and `.terraform/`, so the only way one of those reaches
    the index in real life is `git add -f` -- which is exactly the bypass the
    refusal leg exists to stop. Testing without `-f` would test gitignore.
    """
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(repo, "add", "-f", "--", rel)


# --- token list loading -----------------------------------------------------


def test_list_parsing_drops_comments_and_blanks(tmp_path: Path) -> None:
    path = tmp_path / "list"
    path.write_text(f"# a comment\n\n  {TOKEN_A}  \n{TOKEN_B}\n\n# trailing\n")
    assert mod.load_tokens(path) == [TOKEN_A.lower(), TOKEN_B.lower()]


def test_list_is_lowercased_for_case_insensitive_matching(tmp_path: Path) -> None:
    path = tmp_path / "list"
    path.write_text("MiXeDCaSeToKeN\n")
    assert mod.load_tokens(path) == ["mixedcasetoken"]


def test_missing_list_yields_no_tokens(tmp_path: Path) -> None:
    assert mod.load_tokens(tmp_path / "nope") == []


def test_list_path_prefers_env_then_xdg_then_home(tmp_path: Path) -> None:
    env_path = tmp_path / "from-env"
    xdg = tmp_path / "xdg"
    home = tmp_path / "home"
    (xdg / "dotfiles").mkdir(parents=True)
    (home / ".config" / "dotfiles").mkdir(parents=True)
    xdg_list = xdg / "dotfiles" / "forbidden-tokens"
    home_list = home / ".config" / "dotfiles" / "forbidden-tokens"
    xdg_list.write_text("")
    home_list.write_text("")
    env_path.write_text("")

    assert (
        mod.tokens_path(
            {mod.TOKENS_ENV: str(env_path), "XDG_CONFIG_HOME": str(xdg)},
            home=home,
        )
        == env_path
    )
    assert mod.tokens_path({"XDG_CONFIG_HOME": str(xdg)}, home=home) == xdg_list
    assert mod.tokens_path({}, home=home) == home_list
    assert mod.tokens_path({}, home=tmp_path / "elsewhere") is None


# --- no list => the token scan is a no-op ----------------------------------


def test_no_token_list_passes_even_with_a_would_be_token(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "notes.md", f"leaks {TOKEN_A}\n")
    result = _run(repo, "staged")
    assert result.returncode == 0, result.stderr
    assert "no forbidden-token list" in (result.stdout + result.stderr).lower()


# --- staged content --------------------------------------------------------


def test_staged_added_line_with_a_token_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    _stage(repo, "notes.md", f"first\nleaks {TOKEN_A}\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 1
    assert "notes.md:2" in result.stderr


def test_failure_output_never_prints_the_token_itself(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    _stage(repo, "notes.md", f"leaks {TOKEN_A}\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert TOKEN_A not in combined
    assert TOKEN_A.lower() not in combined.lower()


def test_token_in_a_staged_path_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    _stage(repo, f"tofu/{TOKEN_A}/main.tf", "clean content\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 1
    assert "path" in result.stderr.lower()


def test_untouched_tracked_content_with_a_token_passes(tmp_path: Path) -> None:
    """The six pre-existing tracked occurrences must not fail every commit."""
    repo = _init_repo(tmp_path)
    legacy = repo / "legacy.md"
    legacy.write_text(f"historical {TOKEN_A}\n")
    _git(repo, "add", "legacy.md")
    _git(repo, "commit", "-q", "-m", "chore: legacy")
    tokens = _token_list(tmp_path, TOKEN_A)
    _stage(repo, "new.md", "nothing to see\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_appending_a_clean_line_to_a_tainted_file_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tainted = repo / "legacy.md"
    tainted.write_text(f"historical {TOKEN_A}\n")
    _git(repo, "add", "legacy.md")
    _git(repo, "commit", "-q", "-m", "chore: legacy")
    tokens = _token_list(tmp_path, TOKEN_A)
    tainted.write_text(f"historical {TOKEN_A}\nan innocent new line\n")
    _git(repo, "add", "legacy.md")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_removing_a_tainted_line_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tainted = repo / "legacy.md"
    tainted.write_text(f"historical {TOKEN_A}\nkeep\n")
    _git(repo, "add", "legacy.md")
    _git(repo, "commit", "-q", "-m", "chore: legacy")
    tokens = _token_list(tmp_path, TOKEN_A)
    tainted.write_text("keep\n")
    _git(repo, "add", "legacy.md")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_matching_is_case_insensitive_in_both_directions(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_B)
    _stage(repo, "notes.md", f"leaks {TOKEN_B.lower()}\n")
    assert _run(repo, "staged", token_list=tokens).returncode == 1

    _git(repo, "reset", "-q")
    tokens_lower = _token_list(tmp_path, TOKEN_B.lower())
    _stage(repo, "notes2.md", f"leaks {TOKEN_B.upper()}\n")
    assert _run(repo, "staged", token_list=tokens_lower).returncode == 1


def test_numeric_token_is_matched_inside_a_longer_line(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_NUM)
    _stage(repo, "notes.md", f'project_number = "{TOKEN_NUM}"\n')
    assert _run(repo, "staged", token_list=tokens).returncode == 1


def test_clean_staged_change_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A, TOKEN_B, TOKEN_NUM)
    _stage(repo, "notes.md", "the private project, described in prose only\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_a_world_readable_list_warns_but_still_enforces(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A, mode=0o644)
    _stage(repo, "notes.md", f"leaks {TOKEN_A}\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 1
    assert "0600" in result.stderr


# --- unreviewable blobs (unconditional leg) --------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "tofu/exe-platform/plan.tfplan",
        "tofu/exe-platform/terraform.tfstate",
        "tofu/exe-platform/terraform.tfstate.backup",
        "tofu/exe-platform/terraform.tfstate.1700000000.backup",
        "tofu/exe-platform/terraform.tfvars",
        "tofu/exe-platform/prod.auto.tfvars",
        "tofu/exe-platform/backend.hcl",
        "tofu/exe-platform/.terraform/terraform.tfstate",
    ],
)
def test_unreviewable_paths_are_refused(tmp_path: Path, rel: str) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, rel, "harmless looking text\n")
    result = _run(repo, "staged")
    assert result.returncode == 1, result.stdout
    assert "refus" in result.stderr.lower()


def test_unreviewable_refusal_does_not_need_a_token_list(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "plan.tfplan", "text\n")
    result = _run(repo, "staged")
    assert result.returncode == 1
    assert "plan.tfplan" in result.stderr


@pytest.mark.parametrize(
    "rel",
    [
        "tofu/exe-platform/terraform.tfvars.example",
        "tofu/exe-platform/main.tf",
        "tofu/exe-platform/variables.tf",
        "docs/plan/notes.md",
    ],
)
def test_legitimate_iac_paths_are_not_refused(tmp_path: Path, rel: str) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, rel, "harmless looking text\n")
    result = _run(repo, "staged")
    assert result.returncode == 0, result.stderr


def test_binary_blob_is_refused(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    blob = repo / "snapshot.bin"
    blob.write_bytes(b"\x00\x01\x02binary\x00payload")
    _git(repo, "add", "-f", "snapshot.bin")
    result = _run(repo, "staged")
    assert result.returncode == 1
    assert "binary" in result.stderr.lower()


def test_binary_refusal_has_a_deliberate_escape_hatch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    blob = repo / "snapshot.bin"
    blob.write_bytes(b"\x00\x01\x02binary\x00payload")
    _git(repo, "add", "-f", "snapshot.bin")
    result = _run(repo, "staged", extra_env={mod.ALLOW_BINARY_ENV: "1"})
    assert result.returncode == 0, result.stderr


# --- commit messages -------------------------------------------------------


def test_commit_message_with_a_token_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    msg = repo / "MSG"
    msg.write_text(f"feat: wire up {TOKEN_A}\n")
    result = _run(repo, "commit-msg", str(msg), token_list=tokens)
    assert result.returncode == 1
    assert "commit message" in result.stderr.lower()


def test_clean_commit_message_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    msg = repo / "MSG"
    msg.write_text("feat: wire up the private project\n")
    result = _run(repo, "commit-msg", str(msg), token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_commit_message_git_comment_lines_are_ignored(tmp_path: Path) -> None:
    """git strips `#` lines, so scanning them only produces false positives."""
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    msg = repo / "MSG"
    msg.write_text(
        f"feat: something clean\n\n# On branch {TOKEN_A}\n# Changes staged:\n"
    )
    result = _run(repo, "commit-msg", str(msg), token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_commit_message_body_below_scissors_is_ignored(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    msg = repo / "MSG"
    msg.write_text(
        "feat: clean subject\n\n"
        "# ------------------------ >8 ------------------------\n"
        f"diff --git a/x b/x\n+{TOKEN_A}\n"
    )
    result = _run(repo, "commit-msg", str(msg), token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_commit_msg_mode_needs_a_message_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = _run(repo, "commit-msg", str(repo / "absent"))
    assert result.returncode == 1
    assert "absent" in result.stderr


# --- branch rescan ---------------------------------------------------------


def _branch_repo(tmp_path: Path) -> Path:
    """A repo whose `main` is the merge base of a two-commit feature branch."""
    repo = _init_repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feat/guarded")
    (repo / "a.md").write_text("first\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-q", "-m", "feat: first step")
    return repo


def test_branch_mode_flags_an_earlier_commit_message(tmp_path: Path) -> None:
    repo = _branch_repo(tmp_path)
    (repo / "b.md").write_text("second\n")
    _git(repo, "add", "b.md")
    _git(repo, "commit", "-q", "-m", f"feat: touch {TOKEN_A}")
    (repo / "c.md").write_text("third\n")
    _git(repo, "add", "c.md")
    _git(repo, "commit", "-q", "-m", "feat: clean again")
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "branch", "--base", "main", token_list=tokens)
    assert result.returncode == 1
    assert "commit message" in result.stderr.lower()


def test_branch_mode_flags_an_added_line_from_an_earlier_commit(
    tmp_path: Path,
) -> None:
    repo = _branch_repo(tmp_path)
    (repo / "b.md").write_text(f"leaks {TOKEN_A}\n")
    _git(repo, "add", "b.md")
    _git(repo, "commit", "-q", "-m", "feat: clean subject")
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "branch", "--base", "main", token_list=tokens)
    assert result.returncode == 1
    assert "b.md:1" in result.stderr


def test_branch_mode_passes_on_a_clean_branch(tmp_path: Path) -> None:
    repo = _branch_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A, TOKEN_B)
    result = _run(repo, "branch", "--base", "main", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_branch_mode_ignores_history_before_the_base(tmp_path: Path) -> None:
    """`main`'s nine tainted messages are out of scope by construction."""
    repo = _init_repo(tmp_path)
    (repo / "old.md").write_text("old\n")
    _git(repo, "add", "old.md")
    _git(repo, "commit", "-q", "-m", f"chore: historic {TOKEN_A}")
    _git(repo, "checkout", "-q", "-b", "feat/guarded")
    (repo / "new.md").write_text("new\n")
    _git(repo, "add", "new.md")
    _git(repo, "commit", "-q", "-m", "feat: clean")
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "branch", "--base", "main", token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_branch_mode_without_a_resolvable_base_is_a_documented_no_op(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "branch", "-m", "main", "solo")
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "branch", token_list=tokens)
    assert result.returncode == 0
    assert "base" in (result.stdout + result.stderr).lower()


def test_branch_mode_defaults_to_the_origin_main_merge_base(tmp_path: Path) -> None:
    repo = _branch_repo(tmp_path)
    # Fake an `origin/main` remote-tracking ref at the merge base.
    head_of_main = _git(repo, "rev-parse", "main").strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head_of_main)
    (repo / "b.md").write_text("second\n")
    _git(repo, "add", "b.md")
    _git(repo, "commit", "-q", "-m", f"feat: touch {TOKEN_A}")
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "branch", token_list=tokens)
    assert result.returncode == 1
    assert "commit message" in result.stderr.lower()


# --- arbitrary files (PR body) --------------------------------------------


def test_file_mode_flags_a_pr_body(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    body = tmp_path / "pr-body.md"
    body.write_text(f"## Summary\n\nMigrates {TOKEN_A} to ax.\n")
    result = _run(repo, "file", str(body), token_list=tokens)
    assert result.returncode == 1
    assert "pr-body.md:3" in result.stderr


def test_file_mode_passes_a_clean_pr_body(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    body = tmp_path / "pr-body.md"
    body.write_text("## Summary\n\nMigrates the private project to ax.\n")
    result = _run(repo, "file", str(body), token_list=tokens)
    assert result.returncode == 0, result.stderr


def test_file_mode_scans_whole_content_not_just_added_lines(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    body = tmp_path / "pr-body.md"
    body.write_text(f"{TOKEN_A}\n")
    assert _run(repo, "file", str(body), token_list=tokens).returncode == 1


def test_file_mode_reports_a_missing_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tokens = _token_list(tmp_path, TOKEN_A)
    result = _run(repo, "file", str(tmp_path / "absent.md"), token_list=tokens)
    assert result.returncode == 1
    assert "absent.md" in result.stderr


# --- diff parsing ---------------------------------------------------------


def test_added_lines_parses_a_new_file_hunk() -> None:
    diff = (
        "diff --git a/new.md b/new.md\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/new.md\n"
        "@@ -0,0 +1,2 @@\n"
        "+one\n"
        "+two\n"
    )
    assert mod.added_lines(diff) == [("new.md", 1, "one"), ("new.md", 2, "two")]


def test_added_lines_tracks_line_numbers_across_hunks() -> None:
    diff = (
        "diff --git a/f.md b/f.md\n"
        "--- a/f.md\n"
        "+++ b/f.md\n"
        "@@ -1,0 +2 @@\n"
        "+second\n"
        "@@ -9,0 +20,2 @@\n"
        "+twentieth\n"
        "+twentyfirst\n"
    )
    assert mod.added_lines(diff) == [
        ("f.md", 2, "second"),
        ("f.md", 20, "twentieth"),
        ("f.md", 21, "twentyfirst"),
    ]


def test_added_lines_ignores_deletions_and_dev_null_targets() -> None:
    diff = (
        "diff --git a/gone.md b/gone.md\n"
        "deleted file mode 100644\n"
        "--- a/gone.md\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-one\n"
        "-two\n"
    )
    assert mod.added_lines(diff) == []


def test_added_lines_strips_a_mnemonic_prefix() -> None:
    """`diff.mnemonicPrefix` emits `i/` (index) instead of `b/`.

    It is set in this operator's git config, and a `removeprefix("b/")` left
    the letter glued on, so every finding pointed at `i/path:line` -- a
    location no editor can open. Caught by the live end-to-end probe, pinned
    here.
    """
    diff = "diff --git c/f.md i/f.md\n--- c/f.md\n+++ i/f.md\n@@ -1,0 +2 @@\n+second\n"
    assert mod.added_lines(diff) == [("f.md", 2, "second")]


def test_staged_finding_reports_a_plain_path_under_mnemonic_prefix(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "config", "diff.mnemonicPrefix", "true")
    tokens = _token_list(tmp_path, TOKEN_A)
    _stage(repo, "notes.md", f"leaks {TOKEN_A}\n")
    result = _run(repo, "staged", token_list=tokens)
    assert result.returncode == 1
    assert "notes.md:1" in result.stderr
    assert "i/notes.md" not in result.stderr


def test_added_lines_does_not_mistake_the_plus_plus_plus_header() -> None:
    diff = "diff --git a/f.md b/f.md\n--- a/f.md\n+++ b/f.md\n@@ -1 +1 @@\n-old\n+new\n"
    assert mod.added_lines(diff) == [("f.md", 1, "new")]


# --- prek wiring ----------------------------------------------------------


def test_prek_config_declares_both_install_hook_types() -> None:
    config = (_REPO_ROOT / ".pre-commit-config.yaml").read_text()
    assert "default_install_hook_types:" in config
    block = config.split("default_install_hook_types:", 1)[1].split("\n", 1)[0]
    assert "pre-commit" in block
    assert "commit-msg" in block


def test_prek_config_runs_the_guard_at_both_stages() -> None:
    config = (_REPO_ROOT / ".pre-commit-config.yaml").read_text()
    assert "check_forbidden_tokens.py staged" in config
    assert "check_forbidden_tokens.py commit-msg" in config
    assert "stages: [commit-msg]" in config


def test_install_hooks_recipe_installs_the_commit_msg_shim() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text()
    recipe = justfile.split("\ninstall-hooks:", 1)[1].split("\n\n", 1)[0]
    assert "--hook-type commit-msg" in recipe
    assert "--hook-type pre-commit" in recipe


def test_ci_recipe_rescans_the_branch() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text()
    ci_line = next(
        line for line in justfile.splitlines() if line.startswith("ci: check ")
    )
    assert "check-forbidden-tokens-branch" in ci_line


def test_pr_body_check_recipe_exists() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text()
    assert "\ncheck-pr-body " in justfile


@pytest.mark.skipif(shutil.which("prek") is None, reason="prek not on PATH")
def test_prek_install_really_creates_a_commit_msg_hook(tmp_path: Path) -> None:
    """The DoD is "hooks actually installed", so install them for real."""
    repo = _init_repo(tmp_path)
    shutil.copy(
        _REPO_ROOT / ".pre-commit-config.yaml", repo / ".pre-commit-config.yaml"
    )
    subprocess.run(
        ["prek", "install", "--hook-type", "pre-commit", "--hook-type", "commit-msg"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    for hook in ("pre-commit", "commit-msg"):
        path = repo / ".git" / "hooks" / hook
        assert path.is_file(), f"{hook} shim missing"
        assert path.stat().st_mode & stat.S_IXUSR
        assert "prek" in path.read_text()
