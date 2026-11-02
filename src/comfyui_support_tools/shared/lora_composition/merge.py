"""Training-free weighted, top-K and role-aware LoRA update composition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from .analysis import check_composition_compatibility, factor_pairs
from .contracts import LoRAAdapter, LoRARole, MergeMethod


# 責務: [_compress_update: factorize a merged update within a bounded rank]
# 処理: [truncate SVD and distribute singular values symmetrically across A/B factors]
# 引数: [update: dense module update, rank_limit: maximum exported rank]
# 戻り値: [tuple[np.ndarray, np.ndarray]: output A and B factors]
def _compress_update(update: np.ndarray, rank_limit: int) -> tuple[np.ndarray, np.ndarray]:
    if rank_limit <= 0:
        raise ValueError("rank_limit must be positive")
    u, singular, vh = np.linalg.svd(update, full_matrices=False)
    rank = min(rank_limit, int(np.count_nonzero(singular > 0)))
    if rank == 0:
        return np.zeros((1, update.shape[1])), np.zeros((update.shape[0], 1))
    root = np.sqrt(singular[:rank])
    return root[:, None] * vh[:rank], u[:, :rank] * root[None, :]


# 責務: [_combine_layer: apply one composition rule to a target module]
# 処理: [scale source updates and combine weighted, top-K, or role-aware Zip-style values]
# 引数: [contributions: ordered adapter/update pairs, scales: adapter scales, method: merge rule]
# 戻り値: [np.ndarray: composed dense update]
def _combine_layer(
    contributions: Sequence[tuple[LoRAAdapter, np.ndarray]],
    scales: Mapping[str, float],
    method: MergeMethod,
) -> np.ndarray:
    if not contributions:
        raise ValueError("cannot compose an empty layer")
    weighted = [
        (adapter, update * float(scales.get(adapter.name, 1.0)))
        for adapter, update in contributions
    ]
    if method is MergeMethod.WEIGHTED:
        return sum((update for _, update in weighted), np.zeros_like(weighted[0][1]))
    stack = np.stack([update for _, update in weighted], axis=0)
    if method is MergeMethod.TOP_K:
        return np.sum(stack, axis=0)
    if method is MergeMethod.K_LORA:
        normalized = stack / np.maximum(np.linalg.norm(stack, axis=(1, 2), keepdims=True), 1e-12)
        winner = np.argmax(np.abs(normalized), axis=0)
        return np.take_along_axis(stack, winner[None, ...], axis=0)[0]
    if method is MergeMethod.ZIP_STYLE:
        normalized = []
        for adapter, update in weighted:
            norm = float(np.linalg.norm(update))
            role_weight = (
                1.15
                if adapter.role in {LoRARole.SUBJECT, LoRARole.CHARACTER, LoRARole.STYLE}
                else 1.0
            )
            normalized.append(update / max(norm, 1e-12) * role_weight)
        strengths = np.stack([np.abs(update) for update in normalized], axis=0)
        winner = np.argmax(strengths, axis=0)
        chosen = np.take_along_axis(stack, winner[None, ...], axis=0)[0]
        # Keep aligned contributions additive while selecting a dominant owner for conflicts.
        aligned = np.zeros_like(chosen)
        for index, update in enumerate(stack):
            agrees = np.sign(update) == np.sign(chosen)
            aligned += np.where(agrees, update * 0.25, 0.0)
        return chosen + aligned
    if method is MergeMethod.ZIP_LORA:
        row_strengths = []
        for adapter, update in weighted:
            row_norm = np.linalg.norm(update, axis=1)
            normalized_rows = row_norm / max(float(np.linalg.norm(update)), 1e-12)
            role_weight = 1.15 if adapter.role in {LoRARole.SUBJECT, LoRARole.CHARACTER} else 1.0
            row_strengths.append(normalized_rows * role_weight)
        winner = np.argmax(np.stack(row_strengths, axis=0), axis=0)
        chosen = np.stack([stack[winner[row], row, :] for row in range(stack.shape[1])], axis=0)
        aligned = np.zeros_like(chosen)
        for update in stack:
            aligned += np.where(np.sign(update) == np.sign(chosen), update * 0.2, 0.0)
        return chosen + aligned
    raise ValueError(f"unsupported merge method: {method}")


# 責務: [merge_adapters: create a static low-rank LoRA from compatible source adapters]
# 処理: [preflight, compose each shared target, SVD-compress and emit standard A/B tensor keys]
# 引数: [adapters: selected source LoRAs, base_model: target base, scales: global scales, method: algorithm, layer_scales: optional local scales, rank_limit: output rank cap, top_k_fraction: legacy-compatible reserved selector]
# 戻り値: [dict[str, np.ndarray]: merged A/B factor tensors]
def merge_adapters(
    adapters: Sequence[LoRAAdapter],
    base_model: str,
    base_architecture: str | None = None,
    scales: Mapping[str, float] | None = None,
    method: MergeMethod = MergeMethod.WEIGHTED,
    layer_scales: Mapping[str, Mapping[str, float]] | None = None,
    rank_limit: int = 64,
    top_k_fraction: float = 0.25,
) -> dict[str, np.ndarray]:
    if not 0 < top_k_fraction <= 1:
        raise ValueError("top_k_fraction must be in (0, 1]")
    report = check_composition_compatibility(adapters, base_model, base_architecture)
    if not report.compatible:
        reasons = "; ".join(finding.message for finding in report.findings if finding.blocking)
        raise ValueError(f"LoRA compatibility preflight failed: {reasons}")
    scales = scales or {}
    layer_scales = layer_scales or {}
    factor_maps = {adapter.name: factor_pairs(adapter) for adapter in adapters}
    all_layers = sorted(set.union(*(set(items) for items in factor_maps.values())))
    merged: dict[str, np.ndarray] = {}
    for layer in all_layers:
        contributions = []
        reference_shape = None
        for adapter in adapters:
            pair = factor_maps[adapter.name].get(layer)
            if pair is None:
                continue
            a, b = pair
            update = (b @ a) * (adapter.alpha / adapter.rank)
            if reference_shape is None:
                reference_shape = update.shape
            if update.shape != reference_shape:
                raise ValueError(f"LoRA target {layer} has incompatible update shapes")
            local_scale = layer_scales.get(adapter.name, {}).get(layer)
            if not np.isfinite(
                scales.get(adapter.name, 1.0) if local_scale is None else local_scale
            ):
                raise ValueError(f"scale for {adapter.name}/{layer} must be finite")
            contributions.append((adapter, update))
            # Local scales are represented in the common scale map for this single layer below.
        layer_scale_map = {
            adapter.name: layer_scales.get(adapter.name, {}).get(
                layer, scales.get(adapter.name, 1.0)
            )
            for adapter, _ in contributions
        }
        update = _combine_layer(contributions, layer_scale_map, method)
        if method in {MergeMethod.TOP_K, MergeMethod.K_LORA}:
            keep_count = max(1, int(update.size * top_k_fraction))
            flat = update.ravel()
            cutoff = np.partition(np.abs(flat), -keep_count)[-keep_count]
            update = np.where(np.abs(update) >= cutoff, update, 0.0)
        a, b = _compress_update(update, rank_limit)
        merged[f"{layer}.lora_A.weight"] = a.astype(np.float32)
        merged[f"{layer}.lora_B.weight"] = b.astype(np.float32)
    return merged
