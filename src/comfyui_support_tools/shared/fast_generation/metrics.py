"""Durable latency and resource measurements for generation comparisons."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from threading import Lock

_GENERATION_HISTORY_LOCK = Lock()


# {
#   責務: [GenerationMeasurement: 一つの生成試行で観測したmetricを保持する]
#   フィールド: [profile_id, model, duration_seconds, peak_vram_gib, system_ram_gib, prompt_alignment, artifact]
#   処理: [観測不能metricをNoneに保ち, 推測値を保存しない]
# }
@dataclass(frozen=True, slots=True)
class GenerationMeasurement:
    profile_id: str
    model: str
    duration_seconds: float
    peak_vram_gib: float | None
    system_ram_gib: float | None = None
    available_vram_gib: float | None = None
    available_ram_gib: float | None = None
    gpu_name: str | None = None
    cuda_version: str | None = None
    prompt_alignment: float | None = None
    artifact: bool | None = None
    created_at: str = ""

    # {
    #   責務: [__post_init__: measurement valuesをvalidateする]
    #   処理: [known duration, memory, score, and artifact valuesを検証する]
    #   引数: [self: immutable generation observation]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.model.strip():
            raise ValueError("measurement profile and model must not be empty")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("generation duration cannot be negative")
        if self.peak_vram_gib is not None and (
            not math.isfinite(self.peak_vram_gib) or self.peak_vram_gib < 0
        ):
            raise ValueError("peak VRAM must be non-negative when observed")
        if self.system_ram_gib is not None and (
            not math.isfinite(self.system_ram_gib) or self.system_ram_gib <= 0
        ):
            raise ValueError("system RAM must be positive when observed")
        for name, value in (
            ("available_vram_gib", self.available_vram_gib),
            ("available_ram_gib", self.available_ram_gib),
        ):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be non-negative when observed")
        if self.prompt_alignment is not None and not 0 <= self.prompt_alignment <= 1:
            raise ValueError("prompt alignment must be between zero and one")
        if self.artifact is not None and not isinstance(self.artifact, bool):
            raise TypeError("artifact result must be true, false, or unknown")


# {
#   責務: [GenerationHistory: measurement JSONLを追記して永続化する]
#   フィールド: [path, lock]
#   処理: [異なるprofileのgeneration observationをprocess lock下で追記する]
# }
class GenerationHistory:
    # {
    #   責務: [__init__: generation metricの保存先を設定する]
    #   引数: [path: JSONL履歴ファイル]
    #   戻り値: []
    # }
    # {
    #   責務: [__init__: generation history pathを設定する]
    #   処理: [pathをPathとして保持する]
    #   引数: [self: history writer, path: JSONL destination]
    #   戻り値: []
    # }
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    # {
    #   責務: [append: 検証済みmeasurementをJSONLへ追記する]
    #   引数: [measurement: 実測値と不明値を保持するrecord]
    #   戻り値: [Path: 書き込んだ履歴ファイル]
    # }
    # {
    #   責務: [append: measurementをJSONLへ追記する]
    #   処理: [record timestampを補い, process lock下でappendする]
    #   引数: [self: history writer, measurement: generation observation]
    #   戻り値: [Path: written history]
    # }
    def append(self, measurement: GenerationMeasurement) -> Path:
        if not isinstance(measurement, GenerationMeasurement):
            raise TypeError("measurement must be a GenerationMeasurement")
        record = asdict(measurement)
        if not record["created_at"]:
            record["created_at"] = datetime.now(timezone.utc).isoformat()
        with _GENERATION_HISTORY_LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as destination:
                destination.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return self._path


# {
#   責務: [quality_per_second: alignment scoreをlatencyで割った参考効率を算出する]
#   引数: [measurement: prompt alignmentが採点済みのrun]
#   戻り値: [float | None: score未採点またはlatency 0ならNone]
#   注意: [異なるtaskを跨ぐ品質metricとして扱わない]
# }
# {
#   責務: [quality_per_second: prompt alignmentあたりのgeneration latency efficiencyを算出する]
#   処理: [scoreとpositive latencyが既知の場合のみdivideする]
#   引数: [measurement: measured generation observation]
#   戻り値: [float | None: score is unknown or latency is zeroならNone]
# }
def quality_per_second(measurement: GenerationMeasurement) -> float | None:
    if measurement.prompt_alignment is None or measurement.duration_seconds == 0:
        return None
    return measurement.prompt_alignment / measurement.duration_seconds


# {
#   責務: [quality_per_gib: alignment scoreをsampled peak VRAMで割った参考効率を算出する]
#   引数: [measurement: prompt alignmentとpeak memoryが記録されたrun]
#   戻り値: [float | None: 必要なmetricが不明またはVRAMがzeroの場合None]
#   注意: [異なるprompt task間の品質順位として扱わない]
# }
# {
#   責務: [quality_per_gib: prompt alignmentあたりのVRAM efficiencyを算出する]
#   処理: [scoreとpositive peak VRAMが既知の場合のみdivideする]
#   引数: [measurement: measured generation observation]
#   戻り値: [float | None: score or VRAM is unknownならNone]
# }
def quality_per_gib(measurement: GenerationMeasurement) -> float | None:
    if measurement.prompt_alignment is None or measurement.peak_vram_gib in {None, 0}:
        return None
    return measurement.prompt_alignment / measurement.peak_vram_gib


# {
#   責務: [GenerationSummary: profile単位のlatency, throughput, VRAM, quality集計を保持する]
#   フィールド: [profile_id, sample_count, average_latency_seconds, images_per_minute, average_peak_vram_gib, artifact_rate, average_prompt_alignment, average_quality_per_second, average_quality_per_gib]
# }
@dataclass(frozen=True, slots=True)
class GenerationSummary:
    profile_id: str
    sample_count: int
    average_latency_seconds: float
    images_per_minute: float
    average_peak_vram_gib: float | None
    artifact_rate: float | None
    average_prompt_alignment: float | None
    average_quality_per_second: float | None
    average_quality_per_gib: float | None


# {
#   責務: [summarize_generation_history: JSONL benchmark履歴をprofileごとに集計する]
#   処理: [latencyとVRAMは実測記録のみ集約し, 未採点quality/artifactはNoneのままにする]
#   引数: [path: generation_history.jsonl path]
#   戻り値: [tuple[GenerationSummary, ...]: profile IDの辞書順集計]
#   エラー: [ValueError: recordが壊れている場合]
# }
def summarize_generation_history(path: str | Path) -> tuple[GenerationSummary, ...]:
    grouped: dict[str, list[GenerationMeasurement]] = {}
    source = Path(path)
    if not source.exists():
        return ()
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            measurement = GenerationMeasurement(
                profile_id=record["profile_id"],
                model=record["model"],
                duration_seconds=record["duration_seconds"],
                peak_vram_gib=record.get("peak_vram_gib"),
                system_ram_gib=record.get("system_ram_gib"),
                available_vram_gib=record.get("available_vram_gib"),
                available_ram_gib=record.get("available_ram_gib"),
                gpu_name=record.get("gpu_name"),
                cuda_version=record.get("cuda_version"),
                prompt_alignment=record.get("prompt_alignment"),
                artifact=record.get("artifact"),
                created_at=record.get("created_at", ""),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid generation history record at line {line_number}") from error
        grouped.setdefault(measurement.profile_id, []).append(measurement)
    summaries = []
    for profile_id, measurements in sorted(grouped.items()):
        latencies = [item.duration_seconds for item in measurements]
        positive_latencies = [value for value in latencies if value > 0]
        peaks = [item.peak_vram_gib for item in measurements if item.peak_vram_gib is not None]
        artifact_values = [item.artifact for item in measurements if item.artifact is not None]
        alignment_values = [
            item.prompt_alignment for item in measurements if item.prompt_alignment is not None
        ]
        quality_rates = [
            value for item in measurements if (value := quality_per_second(item)) is not None
        ]
        quality_per_gib_values = [
            value for item in measurements if (value := quality_per_gib(item)) is not None
        ]
        average_latency = fmean(latencies)
        summaries.append(
            GenerationSummary(
                profile_id=profile_id,
                sample_count=len(measurements),
                average_latency_seconds=average_latency,
                images_per_minute=60 / fmean(positive_latencies) if positive_latencies else 0,
                average_peak_vram_gib=fmean(peaks) if peaks else None,
                artifact_rate=fmean(artifact_values) if artifact_values else None,
                average_prompt_alignment=fmean(alignment_values) if alignment_values else None,
                average_quality_per_second=fmean(quality_rates) if quality_rates else None,
                average_quality_per_gib=(
                    fmean(quality_per_gib_values) if quality_per_gib_values else None
                ),
            )
        )
    return tuple(summaries)
