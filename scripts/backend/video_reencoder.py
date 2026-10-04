from __future__ import annotations

import json
import subprocess
import re
from pathlib import Path

from .process_cpu_limiter import ProcessCpuLimiter


# {
# 責務: [VideoReencoder: ffprobe情報と設定から動画再encode用ffmpeg commandを構成・実行する]
# フィールド: [CODECS: codec設定名からffmpeg codec名への対応]
# 処理: [1: source動画の長さ・streamを調べる, 2: size制約に応じた設定を作る,
# 3: 全体またはscene単位のcommandを実行する]
# }
class VideoReencoder:
    """動画の再エンコード用ffmpegコマンドを構築して実行する。"""

    CODECS = {"h264": "libx264", "h265": "libx265"}

    # {
    # 責務: [duration_seconds: ffprobeから動画durationを秒で取得する]
    # 処理: [1: format情報をJSON取得する, 2: duration値をfloatへ変換する]
    # 引数: [source: 調査する動画path]
    # 戻り値: [動画duration秒]
    # }
    @staticmethod
    def duration_seconds(source: Path) -> float:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-print_format", "json", str(source)], capture_output=True, text=True, encoding="utf-8", check=True)
        return float(json.loads(result.stdout)["format"]["duration"])

    # {
    # 責務: [probe_video: ffprobeから動画の主要streamとformat metadataを抽出する]
    # 処理: [1: stream・format情報をJSON取得する, 2: video streamと数値metadataを選ぶ]
    # 引数: [source: 調査する動画path]
    # 戻り値: [解像度・bitrate等を含むmetadata]
    # }
    @staticmethod
    def probe_video(source: Path) -> dict[str, float | int]:
        """Read duration and first video-stream dimensions with ffprobe."""
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-print_format", "json", str(source)], capture_output=True, text=True, encoding="utf-8", check=True)
        data = json.loads(result.stdout); stream = next(item for item in data.get("streams", []) if item.get("codec_type") == "video")
        return {"width": int(stream.get("width", 0)), "height": int(stream.get("height", 0)), "duration": float(data.get("format", {}).get("duration", 0.0))}

    # {
    # 責務: [recommend_settings: source metadataから再encode設定の初期候補を選ぶ]
    # 処理: [1: 解像度等を参照する, 2: codec・preset・最大高・CRF設定を返す]
    # 引数: [metadata: probe_video等で取得した動画情報]
    # 戻り値: [再encode用codec・preset・resolution・quality設定]
    # }
    @staticmethod
    def recommend_settings(metadata: dict[str, float | int]) -> dict[str, str | int]:
        """Recommend conservative encoder settings from source resolution."""
        height = int(metadata.get("height", 0))
        if height >= 2160: return {"codec": "h265", "preset": "slow", "max_height": 1080, "crf": 27}
        if height >= 1440: return {"codec": "h265", "preset": "medium", "max_height": 1080, "crf": 25}
        if height >= 1080: return {"codec": "h264", "preset": "medium", "max_height": 1080, "crf": 23}
        return {"codec": "h264", "preset": "fast", "max_height": 0, "crf": 22}

    # {
    # 責務: [target_video_kbps: 目標file sizeからvideo bitrateを逆算する]
    # 処理: [1: 総bitrate予算をdurationで求める, 2: audio bitrateを差し引き最低値を適用する]
    # 引数: [target_mb: 目標size megabyte, duration_seconds: 動画秒数, audio_kbps: 音声bitrate]
    # 戻り値: [video向け目標bitrate kbps]
    # }
    @staticmethod
    def target_video_kbps(target_mb: float, duration_seconds: float, audio_kbps: int) -> int:
        return max(250, int(target_mb * 8000 / duration_seconds - audio_kbps))

    # {
    # 責務: [build_command: 全体動画向けffmpeg encode commandを構築する]
    # 処理: [1: codecとpresetを選ぶ, 2: resize・quality・audio・size optionを付加する]
    # 引数: [source: 入力動画, target: 出力動画, settings: encode設定,
    # duration_seconds: bitrate計算用duration]
    # 戻り値: [ffmpeg実行引数一覧]
    # }
    def build_command(self, source: Path, target: Path, settings: dict, duration_seconds: float) -> list[str]:
        codec = self.CODECS[settings["codec"]]
        command = ["ffmpeg", "-y", "-i", str(source), "-c:v", codec, "-preset", settings["preset"]]
        if settings["max_height"] > 0:
            command.extend(["-vf", f"scale=-2:min(ih,{settings['max_height']})"])
        if settings["target_mb"] > 0:
            bitrate = self.target_video_kbps(settings["target_mb"], duration_seconds, settings["audio_kbps"])
            command.extend(["-b:v", f"{bitrate}k", "-maxrate", f"{bitrate}k", "-bufsize", f"{bitrate * 2}k"])
        else:
            command.extend(["-crf", str(settings["crf"])])
        return [*command, "-c:a", "aac", "-b:a", f"{settings['audio_kbps']}k", "-movflags", "+faststart", str(target)]

    # {
    # 責務: [scene_timestamps: ffmpeg scene-change検出から区切り時刻を抽出する]
    # 処理: [1: thresholdを安全範囲へclampする, 2: ffmpeg select filterを実行する,
    # 3: timestampを一意化して昇順で返す]
    # 引数: [source: sceneを検出する動画, threshold: scene-change感度]
    # 戻り値: [scene-change時刻の秒一覧]
    # }
    def scene_timestamps(self, source: Path, threshold: float) -> list[float]:
        """Return scene-change timestamps reported by ffmpeg showinfo."""
        threshold = min(0.99, max(0.01, float(threshold)))
        result = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(source), "-vf", f"select=gt(scene\\,{threshold}),showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return sorted(set(float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr) if float(value) > 0.1))

    # {
    # 責務: [build_segment_command: 指定範囲だけをencodeするffmpeg commandを構築する]
    # 処理: [1: 全体commandを組み立てる, 2: seek位置と区間長を挿入する]
    # 引数: [source: 入力動画, target: 出力動画, settings: encode設定,
    # start: 区間開始秒, end: 区間終了秒]
    # 戻り値: [ffmpeg実行引数一覧]
    # }
    def build_segment_command(self, source: Path, target: Path, settings: dict, start: float, end: float) -> list[str]:
        """Build an encode command for one scene interval."""
        full = self.build_command(source, target, settings, max(0.1, end - start)); input_index = full.index("-i")
        return [*full[:1], "-y", "-ss", f"{start:.3f}", "-t", f"{max(0.1, end - start):.3f}", *full[input_index:]]

    # {
    # 責務: [run: ffmpeg commandを起動しCPU制限と出力logを管理する]
    # 処理: [1: subprocessを起動する, 2: 要求core制限を適用する, 3: 出力をlogして終了codeを判定する]
    # 引数: [command: 実行するffmpeg引数, cpu_cores: 任意のCPU制限,
    # log: 出力行を通知するcallback]
    # 戻り値: [processが正常終了した場合はTrue]
    # }
    def run(self, command: list[str], cpu_cores: int | None, log) -> bool:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        ProcessCpuLimiter.apply(process.pid, cpu_cores)
        output, _ = process.communicate()
        if output: log(output)
        return process.returncode == 0
