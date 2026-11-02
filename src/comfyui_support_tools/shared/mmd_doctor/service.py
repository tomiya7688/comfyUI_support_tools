"""PMX diagnostics, local repair proposals, motion-suite comparison, and safe export."""

from __future__ import annotations

import json
import math
import os
import struct
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from .contracts import (
    BinaryPatch,
    DiagnosticSeverity,
    ModelDoctorReport,
    MotionEvaluator,
    MotionSuite,
    PmxDiagnostic,
    PmxModel,
    RepairCandidate,
    RepairEvaluation,
)
from .pmx_parser import PmxFormatError, parse_pmx, parse_pmx_bytes


# {
# 責務: [PatchConflictError: PMX doctorの型または処理単位を表す]
# フィールド: [型と診断に必要な状態]
# 処理: [安全なPMX診断・候補生成を支援する]
# }
class PatchConflictError(ValueError):
    """A candidate patch overlaps or no longer matches its PMX source bytes."""


# {
# 責務: [ModelDoctorService: PMX doctorの型または処理単位を表す]
# フィールド: [型と診断に必要な状態]
# 処理: [安全なPMX診断・候補生成を支援する]
# }
class ModelDoctorService:
    """Read-only analysis and byte-local candidate repair for PMX 2.0/2.1."""

    # {
    # 責務: [__init__: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [evaluator, repair_provider: 呼び出しに必要な値]
    # 戻り値: [None: 処理結果]
    # }
    def __init__(
        self, evaluator: MotionEvaluator | None = None, repair_provider: object | None = None
    ) -> None:
        self.evaluator = evaluator
        self.repair_provider = repair_provider

    # {
    # 責務: [analyze: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [path: 呼び出しに必要な値]
    # 戻り値: [tuple[PmxModel, tuple[PmxDiagnostic, ...]]: 処理結果]
    # }
    def analyze(self, path: str | Path) -> tuple[PmxModel, tuple[PmxDiagnostic, ...]]:
        model = parse_pmx(path)
        diagnostics = list(model.diagnostics)
        diagnostics.extend(_weight_diagnostics(model))
        diagnostics.sort(
            key=lambda item: (_severity_order(item.severity), item.category, item.target, item.code)
        )
        return model, tuple(diagnostics)

    # {
    # 責務: [candidates: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [model, diagnostics: 呼び出しに必要な値]
    # 戻り値: [tuple[RepairCandidate, ...]: 処理結果]
    # }
    def candidates(
        self, model: PmxModel, diagnostics: tuple[PmxDiagnostic, ...]
    ) -> tuple[RepairCandidate, ...]:
        groups = _heuristic_patch_groups(model)
        result = [RepairCandidate("Original", "original", ())]
        for name, patches in groups.items():
            if patches:
                result.append(RepairCandidate(name, "heuristic", tuple(patches)))
        for scale in (0.85, 1.15):
            patches = _physics_search_patches(model, scale)
            if patches:
                result.append(
                    RepairCandidate(
                        f"Physics parameter search x{scale:.2f}", "physics_search", tuple(patches)
                    )
                )
        if self.repair_provider is not None:
            propose = getattr(self.repair_provider, "propose", None)
            if callable(propose):
                for name, patches in propose(model, diagnostics):
                    _validate_patches(model.source_bytes, patches)
                    if patches:
                        result.append(RepairCandidate(name, "ml_adapter", tuple(patches)))
        # Combine independent conservative groups for a comparable all-local candidate.
        combined = tuple(patch for patches in groups.values() for patch in patches)
        if combined:
            result.append(RepairCandidate("All conservative heuristics", "combined", combined))
        return tuple(result)

    # {
    # 責務: [evaluate_candidates: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [model, candidates, suite: 呼び出しに必要な値]
    # 戻り値: [tuple[RepairCandidate, ...]: 処理結果]
    # }
    def evaluate_candidates(
        self,
        model: PmxModel,
        candidates: tuple[RepairCandidate, ...],
        suite: MotionSuite | None = None,
    ) -> tuple[RepairCandidate, ...]:
        if self.evaluator is None:
            return candidates
        suite = suite or MotionSuite()
        evaluated = []
        with tempfile.TemporaryDirectory(prefix="mmd-doctor-eval-") as directory:
            for index, candidate in enumerate(candidates):
                try:
                    candidate_bytes = apply_binary_patches(model.source_bytes, candidate.patches)
                    candidate_path = Path(directory) / f"candidate-{index}.pmx"
                    candidate_path.write_bytes(candidate_bytes)
                    metrics = self.evaluator.evaluate(candidate_path, suite)
                    _validate_evaluation(metrics)
                    evaluated.append(replace(candidate, evaluation=metrics))
                except Exception as error:
                    evaluated.append(
                        replace(
                            candidate,
                            evaluation=None,
                            diagnostics=(
                                *candidate.diagnostics,
                                _diagnostic(
                                    "evaluation.failed",
                                    "evaluation",
                                    candidate.name,
                                    str(error),
                                    severity=DiagnosticSeverity.WARNING,
                                ),
                            ),
                        )
                    )
        return tuple(evaluated)

    # {
    # 責務: [select_best: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [candidates: 呼び出しに必要な値]
    # 戻り値: [int | None: 処理結果]
    # }
    def select_best(self, candidates: tuple[RepairCandidate, ...]) -> int | None:
        scored = [
            (candidate.evaluation.score, index)
            for index, candidate in enumerate(candidates)
            if candidate.evaluation is not None
        ]
        if not scored:
            return None
        return max(scored, key=lambda item: item[0])[1]

    # {
    # 責務: [save_candidate: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [model, candidate, output_path: 呼び出しに必要な値]
    # 戻り値: [tuple[Path, Path]: 処理結果]
    # }
    def save_candidate(
        self,
        model: PmxModel,
        candidate: RepairCandidate,
        output_path: str | Path,
        *,
        before_diagnostics: tuple[PmxDiagnostic, ...] = (),
        after_diagnostics: tuple[PmxDiagnostic, ...] | None = None,
    ) -> tuple[Path, Path]:
        if not candidate.patches:
            raise ValueError("cannot save the original candidate as a repaired PMX")
        destination = Path(output_path).expanduser().resolve()
        if destination.suffix.casefold() != ".pmx":
            raise ValueError("output path must end in .pmx")
        report_path = destination.with_suffix(".doctor.json")
        if destination.exists() or report_path.exists():
            raise FileExistsError("refusing to overwrite existing PMX or diff report")
        patched = apply_binary_patches(model.source_bytes, candidate.patches)
        parsed_after = parse_pmx_bytes(patched, destination)
        if after_diagnostics is None:
            after_diagnostics = tuple(
                (*parsed_after.diagnostics, *_weight_diagnostics(parsed_after))
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_new(destination, patched)
        report = {
            "source": str(model.source_path) if model.source_path else None,
            "output": str(destination),
            "model_name": model.model_name,
            "pmx_version": model.version,
            "strategy": candidate.strategy,
            "candidate": candidate.name,
            "patches": [
                {
                    "offset": patch.offset,
                    "target": patch.target,
                    "before_hex": patch.expected.hex(),
                    "after_hex": patch.replacement.hex(),
                }
                for patch in candidate.patches
            ],
            "evaluation": asdict(candidate.evaluation) if candidate.evaluation else None,
            "before": [_diagnostic_dict(item) for item in before_diagnostics],
            "after": [_diagnostic_dict(item) for item in after_diagnostics],
        }
        try:
            _atomic_write_new(
                report_path,
                (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination, report_path

    # {
    # 責務: [run: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [path, output_path, suite: 呼び出しに必要な値]
    # 戻り値: [ModelDoctorReport: 処理結果]
    # }
    def run(
        self,
        path: str | Path,
        output_path: str | Path,
        suite: MotionSuite | None = None,
    ) -> ModelDoctorReport:
        model, diagnostics = self.analyze(path)
        candidates = self.candidates(model, diagnostics)
        candidates = self.evaluate_candidates(model, candidates, suite)
        selected = self.select_best(candidates)
        warnings = []
        output = report_path = None
        if self.evaluator is None:
            warnings.append(
                "No motion/physics evaluator is configured; repair candidates require manual review and are not auto-applied."
            )
        elif selected is None:
            warnings.append("No repair candidate completed motion-suite evaluation.")
        elif selected == 0 or not candidates[selected].patches:
            warnings.append(
                "The original PMX scored at least as well as every repair candidate; no output was written."
            )
        else:
            output_file, diff_file = self.save_candidate(
                model,
                candidates[selected],
                output_path,
                before_diagnostics=diagnostics,
            )
            output, report_path = str(output_file), str(diff_file)
        return ModelDoctorReport(
            str(model.source_path or ""),
            model.model_name,
            model.version,
            diagnostics,
            candidates,
            selected,
            output,
            report_path,
            tuple(warnings),
        )


# {
# 責務: [apply_binary_patches: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [source, patches: 呼び出しに必要な値]
# 戻り値: [bytes: 処理結果]
# }
def apply_binary_patches(source: bytes, patches: tuple[BinaryPatch, ...]) -> bytes:
    _validate_patches(source, patches)
    output = bytearray(source)
    for patch in patches:
        output[patch.offset : patch.offset + len(patch.expected)] = patch.replacement
    return bytes(output)


# {
# 責務: [_validate_patches: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [source, patches: 呼び出しに必要な値]
# 戻り値: [None: 処理結果]
# }
def _validate_patches(source: bytes, patches: tuple[BinaryPatch, ...]) -> None:
    ordered = sorted(patches, key=lambda item: item.offset)
    previous_end = -1
    for patch in ordered:
        if patch.offset < 0 or len(patch.expected) != len(patch.replacement):
            raise PatchConflictError(f"invalid size/offset for patch {patch.target}")
        end = patch.offset + len(patch.expected)
        if end > len(source) or patch.offset < previous_end:
            raise PatchConflictError(f"patch overlap or out-of-range edit at {patch.target}")
        if source[patch.offset : end] != patch.expected:
            raise PatchConflictError(f"source bytes changed at {patch.target}")
        previous_end = end


# {
# 責務: [_weight_diagnostics: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [model: 呼び出しに必要な値]
# 戻り値: [list[PmxDiagnostic]: 処理結果]
# }
def _weight_diagnostics(model: PmxModel) -> list[PmxDiagnostic]:
    diagnostics = []
    bone_count = len(model.bones)
    for vertex in model.vertices:
        if any(not math.isfinite(value) for value in vertex.position):
            diagnostics.append(
                _diagnostic(
                    "mesh.non_finite_position",
                    "mesh",
                    f"vertex:{vertex.index}",
                    "Vertex position is non-finite",
                )
            )
        invalid = tuple(bone for bone in vertex.bone_indices if bone < 0 or bone >= bone_count)
        if invalid:
            diagnostics.append(
                _diagnostic(
                    "weight.invalid_bone",
                    "weights",
                    f"vertex:{vertex.index}",
                    "Vertex weight references a missing bone",
                    bones=invalid,
                )
            )
        if vertex.weight_type in (2, 4):
            total = sum(vertex.weights)
            if any(not math.isfinite(weight) for weight in vertex.weights):
                diagnostics.append(
                    _diagnostic(
                        "weight.non_finite",
                        "weights",
                        f"vertex:{vertex.index}",
                        "BDEF4/QDEF contains a non-finite influence weight",
                    )
                )
            elif total <= 1e-8:
                diagnostics.append(
                    _diagnostic(
                        "weight.unweighted",
                        "weights",
                        f"vertex:{vertex.index}",
                        "BDEF4/QDEF vertex has no positive influence",
                        weights=vertex.weights,
                    )
                )
            elif abs(total - 1.0) > 0.05:
                diagnostics.append(
                    _diagnostic(
                        "weight.sum",
                        "weights",
                        f"vertex:{vertex.index}",
                        "BDEF4/QDEF weights do not sum to one",
                        total=total,
                    )
                )
        elif vertex.weight_type in (1, 3):
            if not math.isfinite(vertex.weights[0]):
                diagnostics.append(
                    _diagnostic(
                        "weight.non_finite",
                        "weights",
                        f"vertex:{vertex.index}",
                        "BDEF2/SDEF influence weight is non-finite",
                    )
                )
            elif not 0 <= vertex.weights[0] <= 1:
                diagnostics.append(
                    _diagnostic(
                        "weight.out_of_range",
                        "weights",
                        f"vertex:{vertex.index}",
                        "BDEF2/SDEF first influence is outside [0, 1]",
                        weight=vertex.weights[0],
                    )
                )
    boundary_edges = 0
    for triangle in model.faces:
        if any(index < 0 or index >= len(model.vertices) for index in triangle):
            continue
        for left, right in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            if _weight_distance(model.vertices[left], model.vertices[right]) >= 1.5:
                boundary_edges += 1
    if boundary_edges >= 3:
        diagnostics.append(
            _diagnostic(
                "weight.sudden_boundary",
                "weights",
                "mesh",
                "Multiple adjacent face edges have abrupt influence changes",
                edge_count=boundary_edges,
            )
        )
    return diagnostics


# {
# 責務: [_weight_distance: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [first, second: 呼び出しに必要な値]
# 戻り値: [float: 処理結果]
# }
def _weight_distance(first, second) -> float:
    first_map = _normalized_influences(first)
    second_map = _normalized_influences(second)
    return sum(
        abs(first_map.get(index, 0.0) - second_map.get(index, 0.0))
        for index in first_map.keys() | second_map.keys()
    )


# {
# 責務: [_normalized_influences: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [vertex: 呼び出しに必要な値]
# 戻り値: [dict[int, float]: 処理結果]
# }
def _normalized_influences(vertex) -> dict[int, float]:
    values = {}
    for bone, weight in zip(vertex.bone_indices, vertex.weights, strict=True):
        if bone >= 0 and weight > 0:
            values[bone] = values.get(bone, 0.0) + weight
    total = sum(values.values())
    return {bone: weight / total for bone, weight in values.items()} if total else {}


# {
# 責務: [_heuristic_patch_groups: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [model: 呼び出しに必要な値]
# 戻り値: [dict[str, list[BinaryPatch]]: 処理結果]
# }
def _heuristic_patch_groups(model: PmxModel) -> dict[str, list[BinaryPatch]]:
    weights: list[BinaryPatch] = []
    skeleton: list[BinaryPatch] = []
    physics: list[BinaryPatch] = []
    bone_count = len(model.bones)
    root = next((bone.index for bone in model.bones if bone.parent_index < 0), None)
    for vertex in model.vertices:
        root_fallback = False
        if vertex.weight_type in (2, 4):
            if not all(math.isfinite(weight) for weight in vertex.weights):
                total = 0.0
            else:
                total = sum(max(weight, 0.0) for weight in vertex.weights)
            if total > 1e-8 and abs(total - 1.0) > 1e-6:
                for weight, offset in zip(vertex.weights, vertex.weight_offsets, strict=True):
                    normalized = max(0.0, weight) / total
                    weights.append(
                        _float_patch(offset, weight, normalized, f"vertex:{vertex.index}:weight")
                    )
            elif (
                total <= 1e-8
                and root is not None
                and all(math.isfinite(weight) for weight in vertex.weights)
            ):
                root_fallback = True
                for slot, (bone, offset) in enumerate(
                    zip(vertex.bone_indices, vertex.bone_offsets, strict=True)
                ):
                    replacement = root if slot == 0 else -1
                    if bone != replacement:
                        weights.append(
                            _index_patch(
                                offset,
                                _bone_index_size(model, offset),
                                bone,
                                replacement,
                                f"vertex:{vertex.index}:bone:{slot}",
                            )
                        )
                for slot, offset in enumerate(vertex.weight_offsets):
                    weights.append(
                        _float_patch(
                            offset,
                            vertex.weights[slot],
                            1.0 if slot == 0 else 0.0,
                            f"vertex:{vertex.index}:weight",
                        )
                    )
        elif (
            vertex.weight_type in (1, 3)
            and math.isfinite(vertex.weights[0])
            and not 0 <= vertex.weights[0] <= 1
        ):
            normalized = min(1.0, max(0.0, vertex.weights[0]))
            weights.append(
                _float_patch(
                    vertex.weight_offsets[0],
                    vertex.weights[0],
                    normalized,
                    f"vertex:{vertex.index}:weight",
                )
            )
        if not root_fallback:
            for bone_index, offset in zip(vertex.bone_indices, vertex.bone_offsets, strict=True):
                if (bone_index < 0 or bone_index >= bone_count) and root is not None:
                    weights.append(
                        _index_patch(
                            offset,
                            _bone_index_size(model, offset),
                            bone_index,
                            root,
                            f"vertex:{vertex.index}:bone",
                        )
                    )
    for bone in model.bones:
        if bone.parent_index >= bone_count or bone.parent_index == bone.index:
            skeleton.append(
                _index_patch(
                    bone.parent_offset,
                    _bone_index_size(model, bone.parent_offset),
                    bone.parent_index,
                    -1,
                    f"bone:{bone.index}:parent",
                )
            )
    for body in model.rigid_bodies:
        for name, value, offset in zip(
            ("mass", "linear_damping", "angular_damping", "restitution", "friction"),
            (body.mass, body.linear_damping, body.angular_damping, body.restitution, body.friction),
            body.value_offsets,
            strict=True,
        ):
            if not math.isfinite(value):
                continue
            maximum = 1.0 if name in ("restitution", "friction") else max(value, 0.0)
            repaired = min(maximum, max(0.0, value))
            if not math.isclose(value, repaired):
                physics.append(_float_patch(offset, value, repaired, f"rigid:{body.index}:{name}"))
    for joint in model.joints:
        for low, high, low_offset, high_offset in zip(
            joint.minimum, joint.maximum, joint.minimum_offsets, joint.maximum_offsets, strict=True
        ):
            if low > high:
                physics.append(
                    _float_patch(low_offset, low, high, f"joint:{joint.index}:limit_min")
                )
                physics.append(
                    _float_patch(high_offset, high, low, f"joint:{joint.index}:limit_max")
                )
    return {
        "Weight normalization and root fallback": weights,
        "Broken bone parents": skeleton,
        "Physics bounds and joint limits": physics,
    }


# {
# 責務: [_physics_search_patches: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [model, scale: 呼び出しに必要な値]
# 戻り値: [list[BinaryPatch]: 処理結果]
# }
def _physics_search_patches(model: PmxModel, scale: float) -> list[BinaryPatch]:
    patches = []
    for body in model.rigid_bodies:
        for name, value, offset in zip(
            ("mass", "linear_damping", "angular_damping"),
            (body.mass, body.linear_damping, body.angular_damping),
            body.value_offsets[:3],
            strict=True,
        ):
            if math.isfinite(value) and value > 0:
                upper = 10_000.0 if name == "mass" else 1.0
                adjusted = min(upper, max(0.0, value * scale))
                if not math.isclose(value, adjusted):
                    patches.append(
                        _float_patch(offset, value, adjusted, f"rigid:{body.index}:{name}")
                    )
    return patches


# {
# 責務: [_bone_index_size: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [model, offset: 呼び出しに必要な値]
# 戻り値: [int: 処理結果]
# }
def _bone_index_size(model: PmxModel, offset: int) -> int:
    del offset
    return model.bone_index_size


# {
# 責務: [_index_patch: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [offset, size, before, after, target: 呼び出しに必要な値]
# 戻り値: [BinaryPatch: 処理結果]
# }
def _index_patch(offset: int, size: int, before: int, after: int, target: str) -> BinaryPatch:
    code = {1: "b", 2: "h", 4: "i"}.get(size)
    if code is None:
        raise PmxFormatError(f"invalid signed bone index size {size}")
    return BinaryPatch(
        offset, struct.pack("<" + code, before), struct.pack("<" + code, after), target
    )


# {
# 責務: [_float_patch: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [offset, before, after, target: 呼び出しに必要な値]
# 戻り値: [BinaryPatch: 処理結果]
# }
def _float_patch(offset: int, before: float, after: float, target: str) -> BinaryPatch:
    return BinaryPatch(offset, struct.pack("<f", before), struct.pack("<f", after), target)


# {
# 責務: [_validate_evaluation: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [evaluation: 呼び出しに必要な値]
# 戻り値: [None: 処理結果]
# }
def _validate_evaluation(evaluation: RepairEvaluation) -> None:
    for name in ("score", "penetration", "stretch", "jitter", "settling_time"):
        value = getattr(evaluation, name)
        if not math.isfinite(value) or value < 0 or (name == "score" and value > 1):
            raise ValueError(f"invalid motion evaluation metric {name}={value}")


# {
# 責務: [_severity_order: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [severity: 呼び出しに必要な値]
# 戻り値: [int: 処理結果]
# }
def _severity_order(severity: DiagnosticSeverity) -> int:
    return {DiagnosticSeverity.ERROR: 0, DiagnosticSeverity.WARNING: 1, DiagnosticSeverity.INFO: 2}[
        severity
    ]


# {
# 責務: [_diagnostic: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [code, category, target, message, severity: 呼び出しに必要な値]
# 戻り値: [PmxDiagnostic: 処理結果]
# }
def _diagnostic(
    code: str,
    category: str,
    target: str,
    message: str,
    severity=DiagnosticSeverity.ERROR,
    **evidence,
) -> PmxDiagnostic:
    return PmxDiagnostic(code, category, severity, target, message, tuple(sorted(evidence.items())))


# {
# 責務: [_diagnostic_dict: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [item: 呼び出しに必要な値]
# 戻り値: [dict[str, object]: 処理結果]
# }
def _diagnostic_dict(item: PmxDiagnostic) -> dict[str, object]:
    return {
        "code": item.code,
        "category": item.category,
        "severity": item.severity.value,
        "target": item.target,
        "message": item.message,
        "evidence": dict(item.evidence),
    }


# {
# 責務: [_atomic_write_new: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [path, data: 呼び出しに必要な値]
# 戻り値: [None: 処理結果]
# }
def _atomic_write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError:
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
