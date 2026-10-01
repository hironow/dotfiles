"""`just rtk-pi-refresh`: re-vendor rtk's Pi extension after an rtk upgrade.

The installed rtk writes its extension into a throwaway PI_CODING_AGENT_DIR;
vendored() rebuilds config/pi/extensions/rtk.ts from it, keeping the header
(with the new version) and the upstream body verbatim, so installing it still
takes over a file `rtk init` wrote.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ai_tools_check
import install_pi_extensions
import rtk_pi_refresh as refresh

ROOT = Path(__file__).resolve().parents[2]
CURRENT = (ROOT / "config/pi/extensions/rtk.ts").read_text(encoding="utf-8")


def test_the_current_file_round_trips() -> None:
    body = install_pi_extensions.vendored_body(CURRENT)
    assert body is not None
    version = ai_tools_check.vendored_version(CURRENT)
    assert version is not None
    assert refresh.vendored(CURRENT, version, body) == CURRENT


def test_a_new_upstream_body_and_version_replace_the_old_ones() -> None:
    text = refresh.vendored(CURRENT, "0.51.0", "// new upstream\n")
    assert ai_tools_check.vendored_version(text) == "0.51.0"
    assert install_pi_extensions.vendored_body(text) == "// new upstream\n"
    assert text.startswith("// dotfiles-managed: rtk\n")
