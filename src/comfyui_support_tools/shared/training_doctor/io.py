"""Bounded, atomic persistence for Training Doctor reports and resume state."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .contracts import (
    CheckpointAssessment,
    CheckpointRef,
    EvaluationContext,
    ImageMetrics,
    PromptScenario,
    ScorePreset,
    TrainingDoctorReport,
    TrainingTracePoint,
    ValidationSample,
    ValidationTask,
)

_MAX_REPORT_BYTES = 32 * 1024 * 1024


# {
# 責務: [_json_value: convert immutable report contracts into JSON-safe values]
# 処理: [serialize dataclasses, enum values, paths, mappings and sequences recursively]
# 引数: [value: report value to convert]
# 戻り値: [object: JSON-compatible structure]
# }
def _json_value(value: Any) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


# {
# 責務: [save_report: atomically persist training quality and rollback evidence]
# 処理: [serialize bounded UTF-8 JSON, refuse symlinks/implicit overwrite, and replace atomically]
# 引数: [report: completed doctor result, destination: local report path, overwrite: explicit replacement permission]
# 戻り値: [Path: persisted report path]
# エラー: [ValueError: report exceeds the size limit, FileExistsError: destination exists without overwrite]
# }
def save_report(
    report: TrainingDoctorReport, destination: str | Path, overwrite: bool = False
) -> Path:
    path = Path(destination).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("report destination must not be a symbolic link")
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    raw = json.dumps(_json_value(report), ensure_ascii=False, indent=2, sort_keys=True).encode()
    if len(raw) > _MAX_REPORT_BYTES:
        raise ValueError("training doctor report exceeds the 32 MiB storage limit")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as file:
            temporary_path = Path(file.name)
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    return path


# {
# 責務: [_checkpoint: reconstruct one checkpoint identity from validated JSON data]
# 処理: [convert the persisted path and integer step]
# 引数: [value: serialized checkpoint fields]
# 戻り値: [CheckpointRef: immutable checkpoint reference]
# }
def _checkpoint(value: dict[str, Any]) -> CheckpointRef:
    return CheckpointRef(Path(value["path"]), int(value["step"]))


# {
# 責務: [_sample: reconstruct one rendered sample and its evidence]
# 処理: [rebuild checkpoint, prompt, fixed condition and normalized metric contracts]
# 引数: [value: serialized sample fields]
# 戻り値: [ValidationSample: immutable report sample]
# }
def _sample(value: dict[str, Any]) -> ValidationSample:
    context = value["context"]
    scenario_data = context["scenario"]
    scenario = PromptScenario(
        scenario_data["key"],
        scenario_data["prompt"],
        bool(scenario_data["trigger_present"]),
        tuple(scenario_data["concept_labels"]),
        scenario_data.get("trigger_variant", ""),
    )
    evaluation = EvaluationContext(
        scenario,
        int(context["seed"]),
        context["sampler"],
        int(context["inference_steps"]),
        tuple(context["resolution"]),
        float(context["strength"]),
    )
    metrics = ImageMetrics(**value["metrics"])
    preview = Path(value["preview_path"]) if value.get("preview_path") else None
    return ValidationSample(
        _checkpoint(value["checkpoint"]), evaluation, metrics, preview, value.get("sha256")
    )


# {
# 責務: [load_report: restore a bounded immutable Training Doctor report]
# 処理: [reject symlink/oversized/non-object data and reconstruct typed checkpoints, samples, curves and assessments]
# 引数: [source: persisted report path]
# 戻り値: [TrainingDoctorReport: resumable best/current checkpoint decision]
# エラー: [ValueError: report is malformed or exceeds the read limit, OSError: report cannot be read]
# }
def load_report(source: str | Path) -> TrainingDoctorReport:
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_REPORT_BYTES:
        raise ValueError("report must be a bounded regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("training doctor report must be a JSON object")
    assessments = []
    for raw in payload["assessments"]:
        samples = tuple(_sample(item) for item in raw["samples"])
        assessments.append(
            CheckpointAssessment(
                _checkpoint(raw["checkpoint"]),
                float(raw["score"]),
                {key: float(value) for key, value in raw["score_breakdown"].items()},
                float(raw["recommended_strength"]),
                str(raw["recommended_trigger"]),
                tuple(raw["signals"]),
                samples,
            )
        )
    curves = tuple(
        TrainingTracePoint(
            **{**item, "timestep_distribution": tuple(item.get("timestep_distribution", ()))}
        )
        for item in payload["training_curves"]
    )
    return TrainingDoctorReport(
        Path(payload["best_checkpoint"]),
        Path(payload["final_checkpoint"]),
        float(payload["recommended_strength"]),
        str(payload["recommended_trigger"]),
        {key: float(value) for key, value in payload["score_breakdown"].items()},
        int(payload["overfit_onset"]) if payload.get("overfit_onset") is not None else None,
        float(payload["leakage_score"]),
        float(payload["base_preservation"]),
        tuple(_sample(item) for item in payload["validation_samples"]),
        curves,
        str(payload["stop_reason"]),
        tuple(assessments),
        tuple(payload.get("recommended_tags", ())),
        ValidationTask(payload.get("task", ValidationTask.CHARACTER.value)),
        ScorePreset(payload.get("score_preset", ScorePreset.BALANCED.value)),
    )
