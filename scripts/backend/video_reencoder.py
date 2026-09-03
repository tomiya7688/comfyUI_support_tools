from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .process_cpu_limiter import ProcessCpuLimiter


class VideoReencoder:
    """動画の再エンコード用ffmpegコマンドを構築して実行する。"""

    CODECS = {"h264": "libx264", "h265": "libx265"}

    @staticmethod
    def duration_seconds(source: Path) -> float:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-print_format", "json", str(source)], capture_output=True, text=True, encoding="utf-8", check=True)
        return float(json.loads(result.stdout)["format"]["duration"])

    @staticmethod
    def target_video_kbps(target_mb: float, duration_seconds: float, audio_kbps: int) -> int:
        return max(250, int(target_mb * 8000 / duration_seconds - audio_kbps))

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

    def run(self, command: list[str], cpu_cores: int | None, log) -> bool:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        ProcessCpuLimiter.apply(process.pid, cpu_cores)
        output, _ = process.communicate()
        if output: log(output)
        return process.returncode == 0
