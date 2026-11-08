"""Whether this machine's Go can build tools/agent-hooks, for the tests that
build or test it for real (the doctor's real hookrelease check, and the
installed-release recipe)."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# CI's unit job sets this in a step with the module's Go, where a skip would
# hide that a real Go test never ran.
STRICT_GO = os.environ.get("AGENT_HOOKS_STRICT_GO") == "1"


def why_go_cannot_build_the_module(go: str | None, home: Path) -> str:
    """Why this Go cannot build tools/agent-hooks ("" when it can).

    The real-hookrelease test builds with GOTOOLCHAIN=local, as hookrelease
    does, so a Go older than go.mod's `go` line refuses the module. CI's
    unit-test runner has such a system Go. Go can open its telemetry
    counters under the user's config directory even for `go env`, so it runs
    with the given temporary home, outside the module.
    """
    if go is None:
        return "Go is missing"
    go_mod = (ROOT / "tools" / "agent-hooks" / "go.mod").read_text(encoding="utf-8")
    wanted = re.search(r"(?m)^go (\d+(?:\.\d+)*)\s*$", go_mod)
    found = subprocess.run(
        [go, "env", "GOVERSION"],
        cwd=home,
        env={
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "GOCACHE": str(home / ".cache" / "go-build"),
            "GOTOOLCHAIN": "local",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    have = re.match(r"go(\d+(?:\.\d+)*)", found.stdout.strip())
    if wanted is None or have is None:
        return (
            f"cannot tell Go's version: {found.stdout.strip() or found.stderr.strip()}"
        )

    def parts(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    if parts(have[1]) < parts(wanted[1]):
        return f"Go {have[1]} on PATH is older than go.mod's {wanted[1]}"
    return ""
