"""Regression check for justfile shebang-recipe `${VAR:?msg}` env-var
guards.

Why this exists
---------------
The exe-* recipes (`exe-apply`, `exe-plan`, `exe-replace`, ...) all
start with explicit env-var presence checks for `CLOUDFLARE_API_TOKEN`
and `TAILSCALE_API_KEY`:

    : "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"

The intent is to fail fast with a readable message when the operator
forgets to export the provider tokens. The original implementation
used `$${VAR:?msg}` (double-dollar). In a `#!/usr/bin/env bash`
shebang recipe, just does NOT escape `$$` — it passes both characters
through to bash, where `$$` is the PID variable. So
`$${CLOUDFLARE_API_TOKEN:?...}` expanded to
`<pid>{CLOUDFLARE_API_TOKEN:?...}` — a literal string with no
parameter-expansion semantics. The `:?` guard never fired; tofu
ran without provider credentials and bombed inside the apply with
"Missing X-Auth-Key" / "credentials are empty" errors hundreds of
lines deep.

The fix is to use single `$` (`${VAR:?msg}`) in shebang recipes.
This test pins that fix in two ways:

1. Static: no `$${VAR:?...}` pattern anywhere in the justfile.
2. Behavioural: extract one of the exe-* recipes into a tmp
   justfile, run it with the env vars unset, and verify it exits
   non-zero with the expected error message.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JUSTFILE = ROOT / "justfile"


def test_no_double_dollar_var_question_mark_in_shebang_recipes() -> None:
    """`$${VAR:?msg}` is broken in shebang recipes — see module
    docstring. The pattern must not exist anywhere in the justfile."""
    text = JUSTFILE.read_text()
    matches = re.findall(r"\$\$\{[A-Z_][A-Z0-9_]*:\?[^}]*\}", text)
    assert matches == [], (
        "justfile contains broken $${VAR:?msg} env-var guards (these\n"
        "expand to <pid>{VAR:?msg} in shebang recipes — the :? guard\n"
        "never fires). Replace $$ with single $ so bash sees ${VAR:?msg}.\n"
        f"Found: {matches}"
    )


@pytest.fixture
def just_binary() -> str:
    just = shutil.which("just")
    if just is None:
        pytest.skip("just not on PATH")
    return just


def test_env_check_actually_fires_on_missing_token(
    just_binary: str, tmp_path: Path
) -> None:
    """Smoke: a shebang recipe with `${CLOUDFLARE_API_TOKEN:?msg}`
    must exit non-zero when the env var is unset, with the message
    surfaced to stderr."""
    tmp_just = tmp_path / "smoke.just"
    tmp_just.write_text(
        "check:\n"
        "  #!/usr/bin/env bash\n"
        "  set -euo pipefail\n"
        '  : "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"\n'
        '  echo "ok"\n'
    )

    env = {
        # Inherit minimal env, but explicitly unset the token. PATH
        # is required so just can find bash.
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    result = subprocess.run(
        [just_binary, "-f", str(tmp_just), "check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"recipe exited 0 with token unset (expected non-zero).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "set CLOUDFLARE_API_TOKEN before running" in result.stderr, (
        f"expected the :? message in stderr; got:\n{result.stderr}"
    )


def test_env_check_passes_with_token_set(just_binary: str, tmp_path: Path) -> None:
    """Same recipe, with the token set, must succeed."""
    tmp_just = tmp_path / "smoke.just"
    tmp_just.write_text(
        "check:\n"
        "  #!/usr/bin/env bash\n"
        "  set -euo pipefail\n"
        '  : "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN before running}"\n'
        '  echo "ok"\n'
    )

    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "CLOUDFLARE_API_TOKEN": "fake-token-for-test",
    }
    result = subprocess.run(
        [just_binary, "-f", str(tmp_just), "check"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"recipe exited {result.returncode} with token set.\nstderr:\n{result.stderr}"
    )
    assert "ok" in result.stdout
