"""Compatibility and numerical interference analysis for LoRA factors."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..model_identity import ModelFamily, classify_model
from .contracts import CompatibilityFinding, CompatibilityReport, LayerInterference, LoRAAdapter

_MAX_DENSE_UPDATE_ELEMENTS = 8_388_608


# {
# 責務: [_factor_pairs: normalize supported LoRA tensor key conventions]
# 処理: [pair A/B tensors by module path and reject incomplete or ambiguous pairs]
# 引数: [adapter: loaded LoRA artifact]
# 戻り値: [dict[str, tuple[np.ndarray, np.ndarray]]: module factors]
# }
def factor_pairs(adapter: LoRAAdapter) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    pairs: dict[str, dict[str, np.ndarray]] = {}
    for name, tensor in adapter.tensors.items():
        if name.endswith(".lora_A.default.weight") or name.endswith(".lora_A.weight"):
            suffix = (
                ".lora_A.default.weight"
                if name.endswith(".lora_A.default.weight")
                else ".lora_A.weight"
            )
            layer, factor = name[: -len(suffix)], "a"
        elif name.endswith(".lora_B.default.weight") or name.endswith(".lora_B.weight"):
            suffix = (
                ".lora_B.default.weight"
                if name.endswith(".lora_B.default.weight")
                else ".lora_B.weight"
            )
            layer, factor = name[: -len(suffix)], "b"
        elif name.endswith(".lora_down.weight"):
            layer, factor = name[: -len(".lora_down.weight")], "a"
        elif name.endswith(".lora_up.weight"):
            layer, factor = name[: -len(".lora_up.weight")], "b"
        else:
            continue
        array = np.asarray(tensor)
        if array.ndim != 2:
            raise ValueError(f"LoRA factor {name} must be a rank-2 matrix")
        if factor in pairs.setdefault(layer, {}):
            raise ValueError(f"LoRA contains duplicate {factor} factor for {layer}")
        pairs[layer][factor] = array.astype(np.float32, copy=False)
    result = {}
    for layer, factors in pairs.items():
        if set(factors) != {"a", "b"}:
            raise ValueError(f"LoRA layer {layer} has an incomplete A/B factor pair")
        a, b = factors["a"], factors["b"]
        if a.shape[0] != b.shape[1]:
            raise ValueError(f"LoRA layer {layer} has incompatible factor ranks")
        if a.shape[1] * b.shape[0] > _MAX_DENSE_UPDATE_ELEMENTS:
            raise ValueError(f"LoRA layer {layer} exceeds the dense analysis memory limit")
        result[layer] = (a, b)
    if not result:
        raise ValueError(f"LoRA {adapter.name} contains no recognized matrix factors")
    return result


# {
# 責務: [_updates: materialize each adapter's scaled module update]
# 処理: [apply alpha/rank semantics and return deterministic layer matrices]
# 引数: [adapter: loaded LoRA artifact]
# 戻り値: [dict[str, np.ndarray]: full update matrix per module]
# }
def _updates(adapter: LoRAAdapter) -> dict[str, np.ndarray]:
    return {
        layer: (b @ a) * (adapter.alpha / adapter.rank)
        for layer, (a, b) in factor_pairs(adapter).items()
    }


# {
# 責務: [check_composition_compatibility: reject unsafe base and tensor combinations]
# 処理: [compare family, architecture, target overlap, ranks, alpha and provenance evidence]
# 引数: [adapters: selected LoRAs, base_model: requested base identity]
# 戻り値: [CompatibilityReport: blocking errors and nonblocking advisories]
# }
def check_composition_compatibility(
    adapters: Sequence[LoRAAdapter], base_model: str, base_architecture: str | None = None
) -> CompatibilityReport:
    findings: list[CompatibilityFinding] = []
    if len(adapters) < 2:
        findings.append(
            CompatibilityFinding("adapter_count", "At least two LoRAs are required.", True)
        )
    if len({adapter.name for adapter in adapters}) != len(adapters):
        findings.append(
            CompatibilityFinding(
                "duplicate_name", "LoRA names must be unique within a composition.", True
            )
        )
    families = {adapter.family.casefold() for adapter in adapters}
    architectures = {adapter.architecture.casefold() for adapter in adapters}
    if "unknown" in families or "unknown" in architectures:
        findings.append(
            CompatibilityFinding(
                "identity_unknown", "Model family or architecture evidence is unknown.", True
            )
        )
    if len(families) > 1:
        findings.append(
            CompatibilityFinding(
                "family_mismatch", "LoRAs from different base families cannot be merged.", True
            )
        )
    if len(architectures) > 1:
        findings.append(
            CompatibilityFinding(
                "architecture_mismatch", "LoRAs target different base architectures.", True
            )
        )
    if not base_architecture or base_architecture.casefold() == "unknown":
        findings.append(
            CompatibilityFinding(
                "base_architecture_unknown",
                "The target base architecture must be declared before merge.",
                True,
            )
        )
    elif architectures and base_architecture.casefold() not in architectures:
        findings.append(
            CompatibilityFinding(
                "base_architecture_mismatch",
                "LoRA architecture does not match the target base architecture.",
                True,
            )
        )
    base_family = classify_model(base_model).family.value
    if families and base_family not in families and base_family != ModelFamily.UNKNOWN.value:
        findings.append(
            CompatibilityFinding(
                "base_mismatch", "Selected base model family does not match the LoRAs.", True
            )
        )
    factor_maps = {adapter.name: factor_pairs(adapter) for adapter in adapters}
    layer_sets = {adapter.name: set(factor_maps[adapter.name]) for adapter in adapters}
    shared_layers = set.intersection(*layer_sets.values()) if layer_sets else set()
    if not shared_layers:
        findings.append(
            CompatibilityFinding(
                "target_modules",
                "LoRAs target disjoint modules; their updates will be combined independently.",
                False,
            )
        )
    for layer in sorted(set.union(*layer_sets.values()) if layer_sets else set()):
        shapes = {
            (factors[layer][1].shape[0], factors[layer][0].shape[1])
            for factors in factor_maps.values()
            if layer in factors
        }
        if len(shapes) > 1:
            findings.append(
                CompatibilityFinding(
                    "target_shape", f"LoRA target {layer} has incompatible update shapes.", True
                )
            )
    for adapter in adapters:
        if adapter.rank <= 0 or not np.isfinite(adapter.alpha) or adapter.alpha <= 0:
            findings.append(
                CompatibilityFinding(
                    "rank_alpha", f"{adapter.name} has invalid rank or alpha metadata.", True
                )
            )
        if not adapter.provenance:
            findings.append(
                CompatibilityFinding(
                    "provenance_missing", f"{adapter.name} has no source provenance.", False
                )
            )
    if len({adapter.rank for adapter in adapters}) > 1:
        findings.append(
            CompatibilityFinding(
                "rank_difference",
                "Source ranks differ; output rank will be selected independently.",
                False,
            )
        )
    if len({adapter.alpha for adapter in adapters}) > 1:
        findings.append(
            CompatibilityFinding(
                "alpha_difference",
                "Source alpha values differ; each source scale is normalized before merging.",
                False,
            )
        )
    for adapter in adapters:
        factor_ranks = {a.shape[0] for a, _ in factor_maps[adapter.name].values()}
        if factor_ranks != {adapter.rank}:
            findings.append(
                CompatibilityFinding(
                    "rank_metadata_mismatch",
                    f"{adapter.name} rank metadata does not match its tensor factors.",
                    True,
                )
            )
    if not findings:
        findings.append(
            CompatibilityFinding(
                "compatible", "Family, architecture and target modules agree.", False
            )
        )
    return CompatibilityReport(
        compatible=not any(finding.blocking for finding in findings),
        base_model=base_model,
        findings=tuple(findings),
    )


# {
# 責務: [_singular_values: return a bounded singular spectrum summary]
# 処理: [compute stable singular values from one module update]
# 引数: [matrix: materialized LoRA update]
# 戻り値: [tuple[float, ...]: descending spectrum truncated to rank 32]
# }
def _singular_values(matrix: np.ndarray) -> tuple[float, ...]:
    return tuple(float(value) for value in np.linalg.svd(matrix, compute_uv=False)[:32])


# {
# 責務: [_subspace_overlap: estimate shared output subspace coverage]
# 処理: [compare orthonormal bases from the leading left singular vectors]
# 引数: [left: left update, right: right update]
# 戻り値: [float: symmetric overlap in [0, 1]]
# }
def _subspace_overlap(left: np.ndarray, right: np.ndarray) -> float:
    left_u, left_s, _ = np.linalg.svd(left, full_matrices=False)
    right_u, right_s, _ = np.linalg.svd(right, full_matrices=False)
    left_rank = (
        max(1, min(int(np.count_nonzero(left_s > left_s[0] * 1e-6)), 32)) if left_s.size else 0
    )
    right_rank = (
        max(1, min(int(np.count_nonzero(right_s > right_s[0] * 1e-6)), 32)) if right_s.size else 0
    )
    if not left_rank or not right_rank:
        return 0.0
    left_basis, right_basis = left_u[:, :left_rank], right_u[:, :right_rank]
    overlap = np.linalg.norm(left_basis.T @ right_basis, ord="fro") ** 2
    return float(np.clip(overlap / min(left_rank, right_rank), 0.0, 1.0))


# {
# 責務: [analyze_interference: quantify pairwise LoRA update conflict by layer]
# 処理: [compute norm, cosine, subspace, sign-conflict, layer overlap and spectrum]
# 引数: [adapters: compatible or partially overlapping LoRAs]
# 戻り値: [tuple[LayerInterference, ...]: deterministic layer findings]
# }
def analyze_interference(adapters: Sequence[LoRAAdapter]) -> tuple[LayerInterference, ...]:
    updates = {adapter.name: _updates(adapter) for adapter in adapters}
    findings: list[LayerInterference] = []
    for left_index, left_adapter in enumerate(adapters):
        for right_adapter in adapters[left_index + 1 :]:
            left_updates, right_updates = updates[left_adapter.name], updates[right_adapter.name]
            for layer in sorted(set(left_updates) | set(right_updates)):
                if layer not in left_updates or layer not in right_updates:
                    present = left_updates.get(layer, right_updates.get(layer))
                    present_spectrum = _singular_values(present)
                    findings.append(
                        LayerInterference(
                            layer=layer,
                            left=left_adapter.name,
                            right=right_adapter.name,
                            left_update_norm=float(np.linalg.norm(left_updates[layer]))
                            if layer in left_updates
                            else 0.0,
                            right_update_norm=float(np.linalg.norm(right_updates[layer]))
                            if layer in right_updates
                            else 0.0,
                            cosine_similarity=0.0,
                            subspace_overlap=0.0,
                            sign_conflict_fraction=0.0,
                            shared_layer=False,
                            left_singular_values=present_spectrum if layer in left_updates else (),
                            right_singular_values=present_spectrum
                            if layer in right_updates
                            else (),
                        )
                    )
                    continue
                left, right = left_updates[layer], right_updates[layer]
                if left.shape != right.shape:
                    raise ValueError(f"LoRA target {layer} has incompatible update shapes")
                left_flat, right_flat = left.ravel(), right.ravel()
                denom = float(np.linalg.norm(left_flat) * np.linalg.norm(right_flat))
                cosine = float(np.dot(left_flat, right_flat) / denom) if denom else 0.0
                nonzero = (left_flat != 0) & (right_flat != 0)
                conflicts = (
                    float(np.mean(np.sign(left_flat[nonzero]) != np.sign(right_flat[nonzero])))
                    if np.any(nonzero)
                    else 0.0
                )
                findings.append(
                    LayerInterference(
                        layer=layer,
                        left=left_adapter.name,
                        right=right_adapter.name,
                        left_update_norm=float(np.linalg.norm(left_flat)),
                        right_update_norm=float(np.linalg.norm(right_flat)),
                        cosine_similarity=float(np.clip(cosine, -1.0, 1.0)),
                        subspace_overlap=_subspace_overlap(left, right),
                        sign_conflict_fraction=conflicts,
                        shared_layer=True,
                        left_singular_values=_singular_values(left),
                        right_singular_values=_singular_values(right),
                    )
                )
    return tuple(findings)
