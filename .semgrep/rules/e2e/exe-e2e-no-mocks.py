# Test cases for exe-e2e-no-mocks (run via `just semgrep-test`). Each target
# line is preceded by an annotation comment on the line above it: ruleid marks
# an expected match, ok marks an expected non-match.

# ruleid: exe-e2e-no-mocks
import unittest.mock

# ruleid: exe-e2e-no-mocks
from unittest import mock

# ruleid: exe-e2e-no-mocks
from unittest.mock import patch

# ok: exe-e2e-no-mocks
import subprocess


# ruleid: exe-e2e-no-mocks
def test_with_a_patched_environment(monkeypatch):
    monkeypatch.setenv("EXE_E2E", "1")


# ruleid: exe-e2e-no-mocks
def test_with_a_mocker(exe, mocker):
    mocker.patch("subprocess.run")


# ok: exe-e2e-no-mocks
def test_against_the_real_stack(exe):
    subprocess.run(["just", "exe-status"], check=True)
