import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from visualize import find_overlaps, merge_intervals, visualize_rttm


@pytest.fixture
def sample_rttm_content():
    return """SPEAKER sample 1 0.000 1.000 <NA> <NA> speaker1 <NA> <NA>
SPEAKER sample 1 0.500 1.000 <NA> <NA> speaker2 <NA> <NA>
"""


def test_merge_intervals():
    intervals = [
        {"start": 0, "end": 10},
        {"start": 5, "end": 15},
        {"start": 20, "end": 30},
    ]
    merged = merge_intervals(intervals)
    assert len(merged) == 2
    assert merged[0] == {"start": 0, "end": 15}
    assert merged[1] == {"start": 20, "end": 30}


def test_find_overlaps():
    segments = [
        {"start": 0, "end": 10, "speaker": "s1"},
        {"start": 5, "end": 15, "speaker": "s2"},
        {"start": 20, "end": 30, "speaker": "s1"},
    ]
    overlaps = find_overlaps(segments)
    assert len(overlaps) == 1
    assert overlaps[0] == {"start": 5, "end": 10}


def test_visualize_rttm_success(sample_rttm_content):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as rttm_file:
        rttm_file.write(sample_rttm_content)
        rttm_path = rttm_file.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_file:
        img_path = img_file.name

    try:
        with patch("visualize.plt") as mock_plt:
            # Configure subplots to return a tuple (fig, ax)
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)

            visualize_rttm(rttm_path, img_path)

            # Verify plot was saved
            mock_plt.savefig.assert_called_once_with(img_path)

    finally:
        os.remove(rttm_path)
        os.remove(img_path)


def test_visualize_rttm_file_not_found():
    with pytest.raises(SystemExit) as excinfo:
        visualize_rttm("non_existent_file.rttm")
    assert excinfo.value.code == 1
