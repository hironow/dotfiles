"""`mise up` must not queue deferred prunes of the versions it replaces.

Why this exists (2026-09-08, live report)
-----------------------------------------
mise's `upgrade.auto_prune` (default true, `prune_after = "24h"`) makes every
`mise up` schedule the outgoing version for deletion a day later. The prune
then fires from the next activation, i.e. from shell startup. On Windows an
executable that is still running cannot have its directory removed, so on a
box where the old version is still in use (a long-lived Claude Code session,
a bun-hosted tenant process) EVERY new terminal opened with

    WARN  failed to prune npm:@anthropic-ai/claude-code@2.1.258: ...
    WARN  failed to prune bun@1.4.0: ...

and the noise never clears on its own - the queue retries until the holder
exits, which for a tenant process can be weeks. Killing holders on every
`mise up` is not an option, and the warning trains the reader to ignore the
startup output, which is how real activation errors get missed.

The durable fix is to stop queueing prunes at all: old versions stay
installed (harmless, they are just directories) and are reclaimed
deliberately by `just disk-gc` (`mise prune --yes`) at a moment of the
operator's choosing, when it is known that nothing holds them. This keeps
the mise-managed toolset identical on macOS / Linux / Windows - the prune
simply moves from "24h after upgrade, from shell startup" to "on demand".

Static assertion on the shipped config, matching
tests/unit/test_mise_npm_backend.py.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "mise" / "config.toml"


def _settings() -> dict:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("settings", {})


def test_upgrade_does_not_queue_deferred_prunes() -> None:
    """The setting must be an explicit `false`, not merely absent: absent
    means mise's built-in default (true) and the WARN comes back."""
    chosen = _settings().get("upgrade", {}).get("auto_prune")
    assert chosen is False, (
        "config/mise/config.toml must set [settings.upgrade] auto_prune = "
        f"false; found {chosen!r}. With the default (true) every `mise up` "
        "queues the outgoing version for deletion, and on Windows the queued "
        "prune fails at every shell startup for as long as any process still "
        "runs the old executable."
    )


def test_deferred_prune_setting_carries_its_reason() -> None:
    """A bare `auto_prune = false` reads like a leftover and gets tidied
    away; the next reader must see the Windows in-use failure it prevents."""
    text = CONFIG.read_text(encoding="utf-8")
    assert "auto_prune = false" in text
    block = text.split("auto_prune = false", 1)[0]
    assert "disk-gc" in block, (
        "the comment above auto_prune must point at `just disk-gc` as the "
        "deliberate replacement for the automatic prune."
    )
