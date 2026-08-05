#!/usr/bin/env python3
"""Validate the effective Claude settings composed from the fragment layers.

claudelint auto-detects only `.claude/settings.json` (and its .local sibling),
so the layered fragments' `{env, settings}` wrappers cannot be linted directly
(ADR 0037). This checker composes the effective settings.json for every
claude-family profile x OS via `_compose_settings_fragments` (machine-local
layer absent by construction), writes each to `<out>/<profile>-<os>/.claude/`,
and runs `claudelint validate-settings` against each. Wired into
`just lint-claude` and `.github/workflows/claude-lint.yaml`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_agents import (
    AGENTS,
    OS_SETTINGS_OVERLAYS,
    AgentTarget,
    _compose_settings_fragments,
)

CLAUDELINT = ["bunx", "claude-code-lint@0.7.1", "validate-settings", "--no-config"]

# Derived from the script location, NOT sync_agents.DOTFILES_DIR (~/dotfiles):
# CI checks out the repo elsewhere, and the fragments to validate are the ones
# in THIS checkout, not whatever ~/dotfiles happens to hold.
REPO_ROOT = Path(__file__).resolve().parents[1]


def generate(dotfiles_dir: Path, out_dir: Path) -> dict[str, Path]:
    """Write the effective settings.json per claude-family profile x OS.

    Returns ``{"<profile>-<os>": <path to settings.json>}``. The probe agent
    points at a nonexistent home so the machine-local layer is always absent
    (only git-managed layers are validated).
    """
    generated: dict[str, Path] = {}
    for agent in (a for a in AGENTS if a.receives_hooks):
        for system, os_name in OS_SETTINGS_OVERLAYS.items():
            probe = AgentTarget(
                directory=out_dir / "_no-machine-layer",
                name=agent.name,
                key=agent.key,
            )
            composed = _compose_settings_fragments(dotfiles_dir, probe, system=system)
            if composed is None:
                raise SystemExit("no settings fragments found -- nothing to check")
            effective = dict(composed.get("settings", {}))
            if "env" in composed:
                effective["env"] = composed["env"]
            dest = out_dir / f"{agent.key}-{os_name}" / ".claude"
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / "settings.json"
            path.write_text(
                json.dumps(effective, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            generated[f"{agent.key}-{os_name}"] = path
    return generated


def main() -> int:
    """Generate all effective settings and claudelint each one."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        generated = generate(REPO_ROOT, Path(tmp))
        for label, path in sorted(generated.items()):
            result = subprocess.run(
                CLAUDELINT, cwd=path.parents[1], capture_output=True, text=True
            )
            if result.returncode != 0:
                failures.append(label)
                print(f"❌ {label}")
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
            else:
                print(f"✅ {label}")
    if failures:
        print(f"effective settings validation failed: {', '.join(failures)}")
        return 1
    print(f"✅ {len(generated)} effective settings validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
