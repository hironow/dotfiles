"""The Pages site follows docs/agents/web-ui.md and hands out the right commands.

index.html is published at https://hironow.github.io/dotfiles/ and tells people
what to pipe into a shell, so the commands are pinned word for word. The page
uses the platform first and ui-sdk for the copy buttons' pending state and
announcements (ADR-0076), loads ui-sdk only from the vendored, hash-checked copy
(tests/unit/test_site_vendor.py) by relative path (Pages serves the site under
/dotfiles/), and keeps its own script in site/copy.js where vp checks it.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "index.html"
SCRIPT = ROOT / "site" / "copy.js"
VENDOR = ROOT / "site" / "vendor" / "ui-sdk"

INSTALL_BASH = 'bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"'
INSTALL_PWSH = (
    "irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex"
)


class _Page(HTMLParser):
    """Text by element id, every src/href, and every <script> tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: dict[str, str] = {}
        self.links: list[str] = []
        self.scripts: list[dict[str, str | None]] = []
        self._open: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        self.links += [v for k, v in attrs if k in ("src", "href") and v]
        if tag == "script":
            self.scripts.append(found)
        if tag not in ("meta", "link", "br", "img", "input"):
            element_id = found.get("id")
            self._open.append((tag, element_id))
            if element_id:
                self.text[element_id] = ""

    def handle_endtag(self, tag: str) -> None:
        while self._open:
            if self._open.pop()[0] == tag:
                break

    def handle_data(self, data: str) -> None:
        for _tag, element_id in self._open:
            if element_id:
                self.text[element_id] += data


def _page() -> _Page:
    page = _Page()
    page.feed(PAGE.read_text(encoding="utf-8"))
    return page


def _version() -> str:
    (folder,) = [p for p in VENDOR.iterdir() if p.is_dir()]
    return folder.name


def test_the_install_commands_are_the_ones_people_should_run() -> None:
    page = _page()
    assert page.text["cmd-bash"].strip() == INSTALL_BASH
    assert page.text["cmd-pwsh"].strip() == INSTALL_PWSH
    assert (ROOT / "install.sh").is_file() and (ROOT / "bootstrap.ps1").is_file()


def test_ui_sdk_loads_only_from_the_vendored_version_by_relative_path() -> None:
    version = _version()
    page_refs = [ref for ref in _page().links if "ui-sdk" in ref]
    script_refs = re.findall(r'from\s+"([^"]+)"', SCRIPT.read_text(encoding="utf-8"))
    assert {
        "site/vendor/ui-sdk/" + version + "/web.js",
        "site/vendor/ui-sdk/" + version + "/web.css",
    } <= set(page_refs)
    assert script_refs, "site/copy.js imports announce from the vendored core"
    for ref, base in [(r, ROOT) for r in page_refs] + [
        (r, SCRIPT.parent) for r in script_refs
    ]:
        assert not ref.startswith("/") and "://" not in ref, ref
        assert f"vendor/ui-sdk/{version}/" in ref, ref
        assert (base / ref).resolve().is_file(), ref
    for text in (PAGE.read_text(encoding="utf-8"), SCRIPT.read_text(encoding="utf-8")):
        assert "ui-sdk.dev" not in text


def test_the_page_keeps_its_script_in_site_copy_js() -> None:
    page = _page()
    assert all(script.get("src") for script in page.scripts), "no inline <script>"
    assert {"type": "module", "src": "site/copy.js"} in page.scripts
    script = SCRIPT.read_text(encoding="utf-8")
    assert "execCommand" not in script and "execCommand" not in PAGE.read_text(
        encoding="utf-8"
    )
    assert (
        "waitUntil(" in script
        and "announce(" in script
        and "prepareAnnouncements(" in script
    )


def test_copy_buttons_are_ui_buttons_that_hide_until_defined() -> None:
    html = PAGE.read_text(encoding="utf-8")
    for command in ("cmd-bash", "cmd-pwsh"):
        assert re.search(
            rf'<ui-button data-copy="{command}"[^>]*>\s*<button class="copy" type="button">',
            html,
        ), command
    assert re.search(r"ui-button:not\(:defined\)\s*\{\s*display:\s*none;?\s*\}", html)
    assert "aria-label" not in re.sub(r"<nav[^>]*>", "", html), (
        "name buttons by their text"
    )


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git to list tracked files"
)
def test_vp_checks_the_page_script() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    (js_files,) = re.findall(r'^JS_FILES := "(.+)"$', justfile, re.MULTILINE)
    listed = subprocess.run(
        ["git", "-C", "site", "ls-files", "--", *shlex.split(js_files)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.split()
    assert "copy.js" in listed
    assert not [name for name in listed if name.startswith("vendor/")]
