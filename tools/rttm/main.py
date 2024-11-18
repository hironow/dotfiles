#!/usr/bin/env python
import argparse
import pympi # type: ignore
import sys

def convert_rttm_to_eaf(rttm_file: str, output_file: str):
    """
    Convert an RTTM file to an ELAN EAF file.

    Parameters:
    rttm_file (str): Path to the input RTTM file.
    output_file (str): Path to the output EAF file.
    """
    # Read RTTM file
    segments = []
    speakers = set()
    media_filename = None
    with open(rttm_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            tokens = line.split()
            if len(tokens) < 9:
                print(f"Skipping malformed line: {line}", file=sys.stderr)
                continue
            entry_type = tokens[0]
            if entry_type != 'SPEAKER':
                continue
            media_filename = tokens[1]
            start_time = float(tokens[3]) * 1000  # Convert to milliseconds
            duration = float(tokens[4]) * 1000    # Convert to milliseconds
            end_time = start_time + duration
            speaker = tokens[7]
            speakers.add(speaker)
            segments.append({'start': start_time, 'end': end_time, 'speaker': speaker})

    # Create EAF file
    eaf = pympi.Elan.Eaf()

    # Set media file if available
    if media_filename:
        # Determine the mimetype based on the file extension
        extension = media_filename.split('.')[-1].lower()
        mimetypes = {
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'mp4': 'video/mp4',
            'avi': 'video/x-msvideo',
            # 必要に応じて他の拡張子とMIMEタイプを追加
        }
        mimetype = mimetypes.get(extension, 'audio/x-wav')  # デフォルトのMIMEタイプを設定
        eaf.add_linked_file(media_filename, mimetype=mimetype)

    # Create tiers for each speaker
    for speaker in speakers:
        eaf.add_tier(speaker)

    # Add annotations
    for segment in segments:
        start = int(segment['start'])
        end = int(segment['end'])
        speaker = segment['speaker']
        eaf.add_annotation(speaker, start, end, value='')

    # Save EAF file
    eaf.to_file(output_file)
    print(f"EAF file saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Convert an RTTM file to an ELAN EAF file.')
    parser.add_argument('rttm_file', help='Input RTTM file')
    parser.add_argument('output_file', help='Output EAF file')
    args = parser.parse_args()

    convert_rttm_to_eaf(args.rttm_file, args.output_file)

if __name__ == '__main__':
    main()
