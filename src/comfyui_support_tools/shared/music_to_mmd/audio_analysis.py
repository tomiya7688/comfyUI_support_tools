"""Bounded WAV decoding and lightweight tempo/onset/section analysis."""

from __future__ import annotations

import array
import math
import shutil
import statistics
import struct
import subprocess
import sys
import wave
from pathlib import Path

from .contracts import AudioAnalysis, AudioSection, AudioSignal

MAX_AUDIO_BYTES = 256 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
ANALYSIS_RATE = 8000
ENVELOPE_HZ = 50


# {
# 責務: [WavAudioDecoder: decode uncompressed PCM WAV into compact mono float audio]
# フィールド: [maximum bytes and duration bounds]
# 処理: [downmix and decimate while limiting memory for analysis]
# }
class WavAudioDecoder:
    # {
    # 責務: [decode: decode PCM wav with channel/sample-rate/file bounds]
    # 処理: [stream sample chunks, downmix channels, decimate to analysis rate]
    # 引数: [path: wav file path]
    # 戻り値: [AudioSignal: compact mono PCM samples]
    # }
    def decode(self, path: Path) -> AudioSignal:
        source = Path(path)
        if not source.is_file() or source.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError("audio file is missing or exceeds the supported size")
        try:
            stream = wave.open(str(source), "rb")
        except (wave.Error, EOFError) as error:
            raise ValueError(
                "default audio decoder accepts PCM WAV; inject an MP3/FLAC decoder for other formats"
            ) from error
        with stream:
            if stream.getcomptype() != "NONE":
                raise ValueError("WAV decoder only supports uncompressed PCM")
            channels = stream.getnchannels()
            sample_rate = stream.getframerate()
            width = stream.getsampwidth()
            frames = stream.getnframes()
            if (
                channels not in range(1, 9)
                or sample_rate not in range(8000, 192001)
                or width not in {1, 2, 3, 4}
            ):
                raise ValueError("WAV must use 1..8 channels, 8..192 kHz, and 8/16/24/32-bit PCM")
            if frames / sample_rate > MAX_AUDIO_SECONDS:
                raise ValueError("audio duration exceeds the 10-minute analysis limit")
            divisor = max(1, math.ceil(sample_rate / ANALYSIS_RATE))
            output_rate = max(1, round(sample_rate / divisor))
            samples = array.array("f")
            frame_index = 0
            bucket_sum = 0.0
            bucket_count = 0
            while chunk := stream.readframes(min(8192, sample_rate)):
                for sample in _decode_samples(chunk, width):
                    if frame_index % channels == 0:
                        bucket_sum = sample
                    else:
                        bucket_sum += sample
                    if frame_index % channels == channels - 1:
                        mono = bucket_sum / channels
                        if bucket_count % divisor == 0:
                            samples.append(mono)
                        bucket_count += 1
                    frame_index += 1
            if len(samples) < output_rate:
                raise ValueError("audio must contain at least one second of PCM samples")
            return AudioSignal(samples, output_rate)


# {
# 責務: [FFmpegAudioDecoder: decode compressed audio to bounded float PCM]
# フィールド: [ffmpeg executable path]
# 処理: [support MP3/FLAC formats when FFmpeg is installed]
# }
class FFmpegAudioDecoder:
    # {
    # 責務: [__init__: locate optional FFmpeg binary]
    # 処理: [use configured path or PATH discovery]
    # 引数: [executable: optional ffmpeg path]
    # 戻り値: [None: initialized decoder]
    # }
    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("ffmpeg")

    # {
    # 責務: [decode: decode compressed audio using a bounded subprocess]
    # 処理: [emit at most ten minutes of mono 8kHz float32 without shell execution]
    # 引数: [path: MP3/FLAC or FFmpeg-supported audio file]
    # 戻り値: [AudioSignal: compact decoded float PCM]
    # }
    def decode(self, path: Path) -> AudioSignal:
        source = Path(path)
        if not self.executable:
            raise FileNotFoundError(
                "FFmpeg is required for MP3/FLAC; inject another AudioDecoderBackend"
            )
        if not source.is_file() or source.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError("audio file is missing or exceeds the supported size")
        command = (
            self.executable,
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-t",
            str(MAX_AUDIO_SECONDS),
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            str(ANALYSIS_RATE),
            "-f",
            "f32le",
            "pipe:1",
        )
        try:
            result = subprocess.run(command, check=True, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as error:
            raise ValueError("audio decode exceeded the 180-second time limit") from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr[-1000:].decode("utf-8", errors="replace")
            raise ValueError(f"FFmpeg could not decode audio: {detail}") from error
        if not result.stdout or len(result.stdout) > MAX_AUDIO_SECONDS * ANALYSIS_RATE * 4:
            raise ValueError("FFmpeg returned no audio or exceeded the decoded duration limit")
        samples = array.array("f")
        samples.frombytes(result.stdout)
        if len(result.stdout) % 4:
            raise ValueError("FFmpeg returned malformed float audio data")
        if sys.byteorder != "little":
            samples.byteswap()
        return AudioSignal(samples, ANALYSIS_RATE)


# {
# 責務: [AutoAudioDecoder: route uncompressed WAV or compressed formats to decoders]
# フィールド: [WAV decoder, FFmpeg decoder]
# 処理: [select decoder by extension and preserve injection-friendly codec boundaries]
# }
class AutoAudioDecoder:
    # {
    # 責務: [__init__: initialize decoder selection]
    # 処理: [retain WAV and optional FFmpeg adapters]
    # 引数: [wav_decoder: optional PCM decoder, ffmpeg_decoder: optional compressed decoder]
    # 戻り値: [None: initialized decoder router]
    # }
    def __init__(self, wav_decoder=None, ffmpeg_decoder=None):
        self.wav_decoder = wav_decoder or WavAudioDecoder()
        self.ffmpeg_decoder = ffmpeg_decoder or FFmpegAudioDecoder()

    # {
    # 責務: [decode: choose a decoder for the file extension]
    # 処理: [use FFmpeg for MP3/FLAC and WAV reader for PCM WAV]
    # 引数: [path: audio input path]
    # 戻り値: [AudioSignal: decoded mono analysis signal]
    # }
    def decode(self, path: Path) -> AudioSignal:
        if Path(path).suffix.casefold() in {".mp3", ".flac", ".m4a", ".ogg", ".aac"}:
            return self.ffmpeg_decoder.decode(path)
        return self.wav_decoder.decode(path)


# {
# 責務: [_decode_samples: yield normalized signed values from PCM bytes]
# 処理: [decode supported widths without external numerical libraries]
# 引数: [payload: sample bytes, width: bytes per channel sample]
# 戻り値: [iterator: normalized float samples]
# }
def _decode_samples(payload: bytes, width: int):
    if width == 1:
        return ((value - 128) / 128.0 for value in payload)
    if width == 2:
        return (value[0] / 32768.0 for value in struct.iter_unpack("<h", payload))
    if width == 4:
        return (value[0] / 2147483648.0 for value in struct.iter_unpack("<i", payload))
    return (
        int.from_bytes(payload[index : index + 3], "little", signed=True) / 8388608.0
        for index in range(0, len(payload), 3)
    )


# {
# 責務: [analyze_audio: estimate tempo, beat grid, onsets, energy, and coarse sections]
# 処理: [use 20ms RMS energy with autocorrelation and bounded heuristic section labels]
# 引数: [signal: mono PCM, source: provenance path, bpm_override: optional user tempo]
# 戻り値: [AudioAnalysis: timing and structure contract]
# }
def analyze_audio(
    signal: AudioSignal, source: Path, bpm_override: float | None = None
) -> AudioAnalysis:
    if signal.sample_rate <= 0 or not signal.samples:
        raise ValueError("audio signal has no samples or invalid sample rate")
    if len(signal.samples) > signal.sample_rate * MAX_AUDIO_SECONDS or any(
        not math.isfinite(sample) or abs(sample) > 1.5 for sample in signal.samples
    ):
        raise ValueError(
            "audio samples must be finite normalized values within the supported duration"
        )
    duration = len(signal.samples) / signal.sample_rate
    if duration > MAX_AUDIO_SECONDS:
        raise ValueError("audio duration exceeds the analysis limit")
    step = max(1, round(signal.sample_rate / ENVELOPE_HZ))
    energy = []
    samples = signal.samples
    for start in range(0, len(samples), step):
        chunk = samples[start : min(len(samples), start + step)]
        energy.append(math.sqrt(sum(sample * sample for sample in chunk) / len(chunk)))
    if max(energy, default=0.0) < 1e-5:
        raise ValueError("audio signal is silent or below the analysis floor")
    onsets = _detect_onsets(energy)
    bpm = bpm_override if bpm_override is not None else _estimate_bpm(energy)
    if not math.isfinite(bpm) or not 40 <= bpm <= 240:
        raise ValueError("BPM must be within 40..240")
    first_beat = onsets[0] if onsets else 0.0
    interval = 60.0 / bpm
    beats = tuple(
        index * interval + first_beat
        for index in range(math.ceil(max(0.0, duration - first_beat) / interval))
    )
    curve = tuple((index * step / signal.sample_rate, value) for index, value in enumerate(energy))
    sections = _segment_sections(curve, duration)
    return AudioAnalysis(
        duration,
        bpm,
        beats,
        tuple(onsets),
        curve,
        sections,
        Path(source),
        "rms-onset-autocorrelation-v1",
    )


# {
# 責務: [_detect_onsets: detect local positive energy changes]
# 処理: [adaptive median threshold, local peak selection, and minimum spacing]
# 引数: [energy: fixed-rate RMS energy curve]
# 戻り値: [list[float]: onset timestamps in seconds]
# }
def _detect_onsets(energy: list[float]) -> list[float]:
    if len(energy) < 3:
        return []
    flux = [max(0.0, energy[index] - energy[index - 1]) for index in range(1, len(energy))]
    median = statistics.median(flux)
    threshold = max(0.015, median * 1.8)
    selected = []
    last = -10
    for index, value in enumerate(flux):
        if (
            value >= threshold
            and value >= (flux[index - 1] if index else -1)
            and value >= (flux[index + 1] if index + 1 < len(flux) else -1)
            and index - last >= 8
        ):
            selected.append(index / ENVELOPE_HZ)
            last = index
    return selected


# {
# 責務: [_estimate_bpm: estimate tempo from onset autocorrelation]
# 処理: [correlate positive onset flux across valid 40..240 BPM lags]
# 引数: [energy: fixed-rate RMS energy curve]
# 戻り値: [float: estimated tempo in beats per minute]
# }
def _estimate_bpm(energy: list[float]) -> float:
    if len(energy) < 100:
        return 120.0
    flux = [max(0.0, energy[index] - energy[index - 1]) for index in range(1, len(energy))]
    best_lag, best_score = 25, -1.0
    for lag in range(round(ENVELOPE_HZ * 60 / 240), round(ENVELOPE_HZ * 60 / 40) + 1):
        score = sum(flux[index] * flux[index - lag] for index in range(lag, len(flux)))
        if score > best_score:
            best_lag, best_score = lag, score
    bpm = 60 * ENVELOPE_HZ / best_lag
    if bpm < 75:
        bpm *= 2
    elif bpm > 160:
        bpm /= 2
    return min(240.0, max(40.0, bpm))


# {
# 責務: [_segment_sections: produce editable coarse song structure labels]
# 処理: [split at eight-second boundaries and classify energy relative to median]
# 引数: [curve: timestamped energy, duration: total song length]
# 戻り値: [tuple[AudioSection, ...]: ordered sections]
# }
def _segment_sections(
    curve: tuple[tuple[float, float], ...], duration: float
) -> tuple[AudioSection, ...]:
    if duration <= 0:
        return ()
    count = max(1, math.ceil(duration / 8.0))
    energies = []
    for index in range(count):
        start, end = index * 8.0, min(duration, (index + 1) * 8.0)
        block = [energy for time, energy in curve if start <= time < end]
        energies.append(sum(block) / max(len(block), 1))
    median = statistics.median(energies)
    sections = []
    chorus_index = 0
    for index, energy in enumerate(energies):
        start, end = index * 8.0, min(duration, (index + 1) * 8.0)
        if index == 0 and energy < median * 0.8:
            kind = "intro"
        elif index == count - 1 and energy < median * 0.8:
            kind = "outro"
        elif energy >= median * 1.25 and median > 0:
            kind = "chorus"
            chorus_index += 1
        elif index and energies[index - 1] < energy:
            kind = "pre_chorus"
        else:
            kind = "verse"
        sections.append(AudioSection(kind, start, end, energy, f"section-{index:03d}"))
    return tuple(sections)
