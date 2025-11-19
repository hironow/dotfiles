import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def visualize_rttm(
    rttm_file: str, output_file: str | None = None, font_family: str | None = None
) -> None:
    """
    Visualize an RTTM file.

    Parameters:
    rttm_file (str): Path to the input RTTM file.
    output_file (str): Path to the output image file (optional).
    font_family (str): Font family to use for the plot (optional).
    """
    # Set font family
    if font_family:
        plt.rcParams["font.family"] = font_family
    elif sys.platform == "darwin":
        plt.rcParams["font.family"] = "Hiragino Sans"
    else:
        plt.rcParams["font.family"] = "Noto Sans CJK JP"

    rttm_path = Path(rttm_file)
    if not rttm_path.exists():
        logger.error(f"Input file not found: {rttm_file}")
        sys.exit(1)

    # Read RTTM file
    segments: list[dict[str, Any]] = []
    speakers: set[str] = set()

    try:
        with open(rttm_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens = line.split()
                if len(tokens) < 9:
                    logger.warning(f"Skipping malformed line {line_num}: {line}")
                    continue
                entry_type = tokens[0]
                if entry_type != "SPEAKER":
                    continue

                try:
                    start_time = float(tokens[3])
                    duration = float(tokens[4])
                except ValueError:
                    logger.warning(f"Invalid timing data on line {line_num}: {line}")
                    continue

                end_time = start_time + duration
                speaker = tokens[7]
                speakers.add(speaker)
                segments.append(
                    {"start": start_time, "end": end_time, "speaker": speaker}
                )
    except Exception as e:
        logger.error(f"Failed to read RTTM file: {e}")
        sys.exit(1)

    if not segments:
        logger.warning("No valid segments found in RTTM file.")
        return

    # Assign Y coordinates and colors for each speaker
    sorted_speakers = sorted(list(speakers))
    y_positions = {speaker: i for i, speaker in enumerate(sorted_speakers)}
    num_speakers = len(sorted_speakers)

    # Colorblind-friendly palette
    colorblind_friendly_colors = [
        "#0072B2",  # blue
        "#E69F00",  # orange
        "#F0E442",  # yellow
        "#009E73",  # green
        "#56B4E9",  # light blue
        "#D55E00",  # red
        "#CC79A7",  # purple
        "#999999",  # grey
    ]
    cmap = ListedColormap(colorblind_friendly_colors)

    speaker_colors = {
        speaker: cmap(i % len(colorblind_friendly_colors))
        for i, speaker in enumerate(sorted_speakers)
    }

    # Calculate overlaps
    overlapping_segments = find_overlaps(segments)

    # Create figure and axes
    fig_height = max(4, num_speakers + 1)  # Ensure minimum height
    _, ax = plt.subplots(figsize=(12, fig_height))

    # Plot segments for each speaker
    for segment in segments:
        start = segment["start"]
        duration = segment["end"] - segment["start"]
        speaker = segment["speaker"]
        y_pos = y_positions[speaker]
        color = speaker_colors[speaker]
        ax.broken_barh([(start, duration)], (y_pos - 0.4, 0.8), facecolors=color)

    # Plot overlaps (bottom row)
    overlap_y_pos = num_speakers
    for overlap in overlapping_segments:
        start = overlap["start"]
        duration = overlap["end"] - overlap["start"]
        ax.broken_barh(
            [(start, duration)],
            (overlap_y_pos - 0.4, 0.8),
            facecolors="black",
            alpha=0.5,
        )

    # Set labels and title
    ax.set_xlabel("Time (s)")
    ax.set_yticks(list(y_positions.values()) + [overlap_y_pos])
    ax.set_yticklabels(sorted_speakers + ["Overlap"])
    ax.set_title("RTTM Visualization (including overlaps)")

    # Adjust Y limits
    ax.set_ylim(-1, num_speakers + 1)

    # Adjust layout
    plt.tight_layout()

    # Show or save plot
    if output_file:
        try:
            plt.savefig(output_file)
            logger.info(f"Visualization saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save visualization: {e}")
            sys.exit(1)
    else:
        plt.show()


def find_overlaps(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Find overlapping segments.

    Parameters:
    segments (list): List of segments.

    Returns:
    overlaps (list): List of overlapping segments.
    """
    # Sort segments by start time
    sorted_segments = sorted(segments, key=lambda x: x["start"])
    overlaps = []
    n = len(sorted_segments)

    for i in range(n):
        current = sorted_segments[i]
        for j in range(i + 1, n):
            next_seg = sorted_segments[j]
            # Check for overlap
            if current["end"] > next_seg["start"]:
                # Calculate overlap range
                overlap_start = max(current["start"], next_seg["start"])
                overlap_end = min(current["end"], next_seg["end"])
                overlaps.append({"start": overlap_start, "end": overlap_end})
                # Update current end time to extend check
                current["end"] = max(current["end"], next_seg["end"])
            else:
                break  # No more overlaps for this segment

    # Merge overlaps
    merged_overlaps = merge_intervals(overlaps)
    return merged_overlaps


def merge_intervals(intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge overlapping intervals.

    Parameters:
    intervals (list): List of intervals.

    Returns:
    merged (list): List of merged intervals.
    """
    if not intervals:
        return []
    # Sort intervals by start time
    intervals.sort(key=lambda x: x["start"])
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current["start"] <= last["end"]:
            # Merge if overlapping
            last["end"] = max(last["end"], current["end"])
        else:
            merged.append(current)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize an RTTM file.")
    parser.add_argument("rttm_file", help="Input RTTM file")
    parser.add_argument(
        "-o", "--output_file", help="Output image file (optional)", default=None
    )
    parser.add_argument("--font", help="Font family to use (optional)", default=None)
    args = parser.parse_args()

    visualize_rttm(args.rttm_file, args.output_file, args.font)


if __name__ == "__main__":
    main()
