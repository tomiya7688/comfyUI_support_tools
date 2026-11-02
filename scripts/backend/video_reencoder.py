from __future__ import annotations

import json
import subprocess
import re
from pathlib import Path

from .process_cpu_limiter import ProcessCpuLimiter


# {
#   責務: [VideoReencoder: ffmpeg/ffprobe video inspection and encoding operationsを提供する]
#   処理: [settings and scene intervalsからcommandを組み立てprocess outputをlogする]
#   フィールド: [CODECS and encoder command helpers]
# }
class VideoReencoder:
    """動画の再エンコード用ffmpegコマンドを構築して実行する。"""

    CODECS = {"h264": "libx264", "h265": "libx265"}

    # {
    #   責務: [duration_seconds: ffprobeからsource video durationを読み取る]
    #   処理: [format JSONを取得してduration fieldをfloatへ変換する]
    #   引数: [source]
    #   戻り値: [float]
    # }
    @staticmethod
    def duration_seconds(source: Path) -> float:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-print_format", "json", str(source)], capture_output=True, text=True, encoding="utf-8", check=True)
        return float(json.loads(result.stdout)["format"]["duration"])

    # {
    #   責務: [probe_video: ffprobeからvideo duration and first stream dimensionsを読む]
    #   処理: [stream/format JSONをparseしてwidth, height, durationを返す]
    #   引数: [source]
    #   戻り値: [dict[str, float | int]]
    # }
    @staticmethod
    def probe_video(source: Path) -> dict[str, float | int]:
        """Read duration and first video-stream dimensions with ffprobe."""
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-print_format", "json", str(source)], capture_output=True, text=True, encoding="utf-8", check=True)
        data = json.loads(result.stdout); stream = next(item for item in data.get("streams", []) if item.get("codec_type") == "video")
        return {"width": int(stream.get("width", 0)), "height": int(stream.get("height", 0)), "duration": float(data.get("format", {}).get("duration", 0.0))}

    # {
    #   責務: [recommend_settings: source resolutionに基づきconservative encoder settingsを選ぶ]
    #   処理: [height thresholdsでcodec, preset, max height, and CRFを決める]
    #   引数: [metadata]
    #   戻り値: [dict[str, str | int]]
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
    #   責務: [target_video_kbps: target file sizeからaudio bitrate控除後のvideo bitrateを計算する]
    #   処理: [MB and durationをkbpsへ換算し、minimum bitrate 250を適用する]
    #   引数: [target_mb, duration_seconds, audio_kbps]
    #   戻り値: [int]
    # }
    @staticmethod
    def target_video_kbps(target_mb: float, duration_seconds: float, audio_kbps: int) -> int:
        return max(250, int(target_mb * 8000 / duration_seconds - audio_kbps))

    # {
    #   責務: [build_command: settingsからcomplete ffmpeg encoding commandを作る]
    #   処理: [codec, scale, size-target bitrate or CRF, AAC audio, and faststartをconfigureする]
    #   引数: [source, target, settings, duration_seconds]
    #   戻り値: [list[str]]
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
    #   責務: [scene_timestamps: ffmpeg showinfo outputからscene change timestampsを取得する]
    #   処理: [thresholdをclampし、positive timestampsをunique sorted listで返す]
    #   引数: [source, threshold]
    #   戻り値: [list[float]]
    # }
    def scene_timestamps(self, source: Path, threshold: float) -> list[float]:
        """Return scene-change timestamps reported by ffmpeg showinfo."""
        threshold = min(0.99, max(0.01, float(threshold)))
        result = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(source), "-vf", f"select=gt(scene\\,{threshold}),showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return sorted(set(float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr) if float(value) > 0.1))

    # {
    #   責務: [build_segment_command: one scene interval向けffmpeg commandを作る]
    #   処理: [full commandへseek and bounded duration argumentsを挿入する]
    #   引数: [source, target, settings, start, end]
    #   戻り値: [list[str]]
    # }
    def build_segment_command(self, source: Path, target: Path, settings: dict, start: float, end: float) -> list[str]:
        """Build an encode command for one scene interval."""
        full = self.build_command(source, target, settings, max(0.1, end - start)); input_index = full.index("-i")
        return [*full[:1], "-y", "-ss", f"{start:.3f}", "-t", f"{max(0.1, end - start):.3f}", *full[input_index:]]

    # {
    #   責務: [run: ffmpeg processを起動し、outputをlog callbackへ転送する]
    #   処理: [CPU affinityを設定してstdoutを逐次logしexit statusを返す]
    #   引数: [command, cpu_cores, log]
    #   戻り値: [bool]
    # }
    def run(self, command: list[str], cpu_cores: int | None, log) -> bool:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        ProcessCpuLimiter.apply(process.pid, cpu_cores)
        for line in process.stdout or ():
            line = line.rstrip()
            if line:
                log(line)
        return process.wait() == 0
