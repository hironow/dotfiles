#!/usr/bin/env python3
"""Validate the effective Claude settings composed from the fragment layers.

The layered fragments' `{env, settings}` wrappers are not a settings.json
shape any external tool understands (ADR 0037), so this checker composes the
effective settings.json for every claude-family profile x OS via
`_compose_settings_fragments` (machine-local layer absent by construction),
writes each to `<out>/<profile>-<os>/.claude/`, and structurally validates
each one with the stdlib-only `_validate_settings` (the third-party
claudelint that used to do this is retired — ADR 0041). Wired into
`just lint-claude` and `.github/workflows/claude-lint.yaml`.
"""

import json
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


def _configure_output() -> None:
    # Windows Git Bash hands Python a cp932 stdout; the emoji status lines
    # then raise UnicodeEncodeError and kill the checker. Re-encode to UTF-8
    # where supported, degrade to replacement characters elsewhere.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _validate_settings(data: object) -> list[str]:
    """Structural validation of a composed settings.json (stdlib-only).

    Replaces the retired third-party claudelint (ADR 0041). Checks the
    shapes this repo's fragments actually produce — env, permissions,
    hooks — and leaves unknown top-level keys alone (the upstream schema
    evolves; an allowlist would rot into false reds).
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    env = data.get("env")
    if env is not None:
        if not isinstance(env, dict):
            errors.append("env must be an object")
        else:
            errors.extend(
                f"env[{k!r}] must map str -> str"
                for k, v in env.items()
                if not (isinstance(k, str) and isinstance(v, str))
            )
    permissions = data.get("permissions")
    if permissions is not None:
        if not isinstance(permissions, dict):
            errors.append("permissions must be an object")
        else:
            for key in ("allow", "deny", "ask"):
                rules = permissions.get(key)
                if rules is not None and not (
                    isinstance(rules, list) and all(isinstance(r, str) for r in rules)
                ):
                    errors.append(f"permissions.{key} must be a list of str")
            mode = permissions.get("defaultMode")
            if mode is not None and not isinstance(mode, str):
                errors.append("permissions.defaultMode must be a str")
    hooks = data.get("hooks")
    if hooks is not None:
        if not isinstance(hooks, dict):
            errors.append("hooks must be an object")
        else:
            for event, blocks in hooks.items():
                if not isinstance(blocks, list):
                    errors.append(f"hooks.{event} must be a list")
                    continue
                for i, block in enumerate(blocks):
                    where = f"hooks.{event}[{i}]"
                    if not isinstance(block, dict):
                        errors.append(f"{where} must be an object")
                        continue
                    matcher = block.get("matcher")
                    if matcher is not None and not isinstance(matcher, str):
                        errors.append(f"{where}.matcher must be a str")
                    inner = block.get("hooks")
                    if not isinstance(inner, list) or not inner:
                        errors.append(f"{where}.hooks must be a non-empty list")
                        continue
                    for j, hook in enumerate(inner):
                        if not (
                            isinstance(hook, dict)
                            and hook.get("type") == "command"
                            and isinstance(hook.get("command"), str)
                        ):
                            errors.append(
                                f"{where}.hooks[{j}] must be "
                                '{"type": "command", "command": <str>}'
                            )
    return errors


def main() -> int:
    """Generate all effective settings and structurally validate each one."""
    _configure_output()
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        generated = generate(REPO_ROOT, Path(tmp))
        for label, path in sorted(generated.items()):
            try:
                data: object = json.loads(path.read_text(encoding="utf-8"))
                errors = _validate_settings(data)
            except json.JSONDecodeError as exc:
                errors = [f"invalid JSON: {exc}"]
            if errors:
                failures.append(label)
                print(f"❌ {label}")
                for error in errors:
                    print(f"   {error}")
            else:
                print(f"✅ {label}")
    if failures:
        print(f"effective settings validation failed: {', '.join(failures)}")
        return 1
    print(f"✅ {len(generated)} effective settings validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
