import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import pympi  # type: ignore

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def convert_rttm_to_eaf(rttm_file: str, output_file: str) -> None:
    """
    Convert an RTTM file to an ELAN EAF file.

    Parameters:
    rttm_file (str): Path to the input RTTM file.
    output_file (str): Path to the output EAF file.
    """
    rttm_path = Path(rttm_file)
    if not rttm_path.exists():
        logger.error(f"Input file not found: {rttm_file}")
        sys.exit(1)

    # Read RTTM file
    segments: list[dict[str, Any]] = []
    speakers: set[str] = set()
    media_filename: str | None = None

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

                # RTTM format: SPEAKER file 1 onset duration <NA> <NA> speaker <NA> <NA>
                media_filename = tokens[1]
                try:
                    start_time = float(tokens[3]) * 1000  # Convert to milliseconds
                    duration = float(tokens[4]) * 1000  # Convert to milliseconds
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

    # Create EAF file
    eaf = pympi.Elan.Eaf()

    # Set media file if available
    if media_filename:
        # Determine the mimetype based on the file extension
        extension = media_filename.split(".")[-1].lower()
        mimetypes = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "mp4": "video/mp4",
            "avi": "video/x-msvideo",
            "mkv": "video/x-matroska",
        }
        mimetype = mimetypes.get(extension, "audio/x-wav")  # Default to wav if unknown
        eaf.add_linked_file(media_filename, mimetype=mimetype)

    # Create tiers for each speaker
    for speaker in sorted(speakers):
        eaf.add_tier(speaker)

    # Add annotations
    for segment in segments:
        start = int(segment["start"])
        end = int(segment["end"])
        speaker = segment["speaker"]
        eaf.add_annotation(speaker, start, end, value="")

    # Save EAF file
    try:
        eaf.to_file(output_file)
        logger.info(f"EAF file saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save EAF file: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an RTTM file to an ELAN EAF file."
    )
    parser.add_argument("rttm_file", help="Input RTTM file")
    parser.add_argument("output_file", help="Output EAF file")
    args = parser.parse_args()

    convert_rttm_to_eaf(args.rttm_file, args.output_file)


if __name__ == "__main__":
    main()
