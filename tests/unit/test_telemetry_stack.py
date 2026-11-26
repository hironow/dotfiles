"""The local telemetry stack is one upstream grafana/otel-lgtm container.

ADR 0072: dotfiles keeps no collector, backend, or Grafana config of its own,
no dashboards, and no example app. repo-lint holds the policies on the Compose
file, Dependabot, and the lint scopes (telemetry-* and
root-lint-covers-telemetry); these tests check what git tracks and ignores.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_telemetry_tracks_only_compose_readme_and_env_ignore() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "telemetry"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()
    assert sorted(tracked) == [
        "telemetry/.gitignore",
        "telemetry/README.md",
        "telemetry/compose.yaml",
    ]


def test_env_files_next_to_the_compose_file_stay_untracked() -> None:
    # podman-compose reads telemetry/.env; upstream puts OTLP auth headers there.
    result = subprocess.run(
        ["git", "check-ignore", "telemetry/.env", "telemetry/.env.local"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.stdout.split() == ["telemetry/.env", "telemetry/.env.local"]
