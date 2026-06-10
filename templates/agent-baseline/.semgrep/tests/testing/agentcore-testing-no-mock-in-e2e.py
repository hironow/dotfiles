# Test fixture for agentcore-testing-no-mock-in-e2e.
# Semgrep test annotations: a line ending in the rule id after "rule"+"id:" marks
# an expected match; "ok:" + rule id marks an expected non-match. (Worded to
# avoid embedding those literal tokens in this header.)
from unittest import mock
from unittest.mock import MagicMock


def test_uses_mock_is_flagged() -> None:
    # ruleid: agentcore-testing-no-mock-in-e2e
    client = MagicMock()
    assert client is not None


def test_uses_patch_is_flagged(mocker) -> None:
    # ruleid: agentcore-testing-no-mock-in-e2e
    mocker.patch("service.call")


def test_real_dependency_is_ok() -> None:
    # ok: agentcore-testing-no-mock-in-e2e
    client = create_real_client()
    assert client.ping() is True
