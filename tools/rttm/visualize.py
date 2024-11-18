import argparse
import sys
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def visualize_rttm(rttm_file: str, output_file: str | None = None):
    """
    RTTMファイルを可視化します。

    Parameters:
    rttm_file (str): 入力RTTMファイルのパス。
    output_file (str): 可視化結果を保存するファイルのパス（オプション）。
    """
    # 日本語フォントの設定
    plt.rcParams["font.family"] = "Hiragino Sans"  # macOSの場合
    # plt.rcParams['font.family'] = 'Noto Sans CJK JP'  # 他の環境の場合

    # RTTMファイルの読み込み
    segments: list[dict[str, Any]] = []
    speakers: set[str] = set()
    with open(rttm_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            if len(tokens) < 9:
                print(f"不正な行をスキップしました: {line}", file=sys.stderr)
                continue
            entry_type = tokens[0]
            if entry_type != "SPEAKER":
                continue
            start_time = float(tokens[3])
            duration = float(tokens[4])
            end_time = start_time + duration
            speaker = tokens[7]
            speakers.add(speaker)
            segments.append({"start": start_time, "end": end_time, "speaker": speaker})

    # 話者ごとのY座標と色の割り当て
    speakers = sorted(list(speakers))
    y_positions = {speaker: i for i, speaker in enumerate(speakers)}
    num_speakers = len(speakers)

    # 色覚障害者に配慮したカラーパレットの定義
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
        for i, speaker in enumerate(speakers)
    }

    # 重複領域の計算
    overlapping_segments = find_overlaps(segments)

    # 図と軸の作成
    fig_height = num_speakers + 1  # 重複領域の分を追加
    _, ax = plt.subplots(figsize=(12, fig_height))

    # 各話者の発話区間をプロット
    for segment in segments:
        start = segment["start"]
        duration = segment["end"] - segment["start"]
        speaker = segment["speaker"]
        y_pos = y_positions[speaker]
        color = speaker_colors[speaker]
        ax.broken_barh([(start, duration)], (y_pos - 0.4, 0.8), facecolors=color)

    # 重複領域をプロット（最下部の列）
    overlap_y_pos = num_speakers  # 重複領域のY座標
    for overlap in overlapping_segments:
        start = overlap["start"]
        duration = overlap["end"] - overlap["start"]
        ax.broken_barh(
            [(start, duration)],
            (overlap_y_pos - 0.4, 0.8),
            facecolors="black",
            alpha=0.5,
        )

    # ラベルとタイトルの設定
    ax.set_xlabel("時間 (秒)")
    ax.set_yticks(list(y_positions.values()) + [overlap_y_pos])
    ax.set_yticklabels(speakers + ["重複領域"])
    ax.set_title("RTTMファイルの可視化（重複領域を含む）")

    # Y軸の範囲調整
    ax.set_ylim(-1, fig_height)

    # レイアウトの調整
    plt.tight_layout()

    # グラフの表示または保存
    if output_file:
        plt.savefig(output_file)
        print(f"可視化結果を {output_file} に保存しました。")
    else:
        plt.show()


def find_overlaps(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    セグメントのリストから重複している領域を検出します。

    Parameters:
    segments (list): セグメントのリスト。

    Returns:
    overlaps (list): 重複領域のリスト。
    """
    # セグメントを開始時間でソート
    sorted_segments = sorted(segments, key=lambda x: x["start"])
    overlaps = []
    n = len(sorted_segments)

    for i in range(n):
        current = sorted_segments[i]
        for j in range(i + 1, n):
            next_seg = sorted_segments[j]
            # 重複の判定
            if current["end"] > next_seg["start"]:
                # 重複領域の開始と終了を計算
                overlap_start = max(current["start"], next_seg["start"])
                overlap_end = min(current["end"], next_seg["end"])
                overlaps.append({"start": overlap_start, "end": overlap_end})
                # currentの終了時間を更新
                current["end"] = max(current["end"], next_seg["end"])
            else:
                break  # 重複がない場合は次のセグメントへ
    # 重複領域をマージ
    merged_overlaps = merge_intervals(overlaps)
    return merged_overlaps


def merge_intervals(intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    重複している区間をマージします。

    Parameters:
    intervals (list): 区間のリスト。

    Returns:
    merged (list): マージされた区間のリスト。
    """
    if not intervals:
        return []
    # 区間を開始時間でソート
    intervals.sort(key=lambda x: x["start"])
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current["start"] <= last["end"]:
            # 区間が重なっている場合、終了時間を更新
            last["end"] = max(last["end"], current["end"])
        else:
            merged.append(current)
    return merged


def main():
    parser = argparse.ArgumentParser(description="RTTMファイルを可視化します。")
    parser.add_argument("rttm_file", help="入力RTTMファイル")
    parser.add_argument(
        "-o", "--output_file", help="出力画像ファイル（省略可）", default=None
    )
    args = parser.parse_args()

    visualize_rttm(args.rttm_file, args.output_file)


if __name__ == "__main__":
    main()
