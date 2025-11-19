import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from to_eaf import convert_rttm_to_eaf


@pytest.fixture
def sample_rttm_content():
    return """SPEAKER sample 1 0.000 1.000 <NA> <NA> speaker1 <NA> <NA>
SPEAKER sample 1 1.500 2.000 <NA> <NA> speaker2 <NA> <NA>
"""


def test_convert_rttm_to_eaf_success(sample_rttm_content):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as rttm_file:
        rttm_file.write(sample_rttm_content)
        rttm_path = rttm_file.name

    with tempfile.NamedTemporaryFile(delete=False) as eaf_file:
        eaf_path = eaf_file.name

    try:
        # Mock pympi to avoid actual file creation issues and dependency on pympi behavior
        with patch("to_eaf.pympi.Elan.Eaf") as mock_eaf_class:
            mock_eaf = MagicMock()
            mock_eaf_class.return_value = mock_eaf

            convert_rttm_to_eaf(rttm_path, eaf_path)

            # Verify Eaf was initialized
            mock_eaf_class.assert_called_once()

            # Verify tiers were added
            mock_eaf.add_tier.assert_any_call("speaker1")
            mock_eaf.add_tier.assert_any_call("speaker2")

            # Verify annotations were added
            # speaker1: start 0.0 -> 0ms, duration 1.0 -> 1000ms. End = 1000ms
            mock_eaf.add_annotation.assert_any_call("speaker1", 0, 1000, value="")
            # speaker2: start 1.5 -> 1500ms, duration 2.0 -> 2000ms. End = 3500ms
            mock_eaf.add_annotation.assert_any_call("speaker2", 1500, 3500, value="")

            # Verify to_file was called
            mock_eaf.to_file.assert_called_once_with(eaf_path)

    finally:
        os.remove(rttm_path)
        os.remove(eaf_path)


def test_convert_rttm_to_eaf_file_not_found():
    with pytest.raises(SystemExit) as excinfo:
        convert_rttm_to_eaf("non_existent_file.rttm", "output.eaf")
    assert excinfo.value.code == 1
