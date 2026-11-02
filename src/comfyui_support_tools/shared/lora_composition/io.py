"""Bounded, atomic persistence for recipes, preferences and merged weights."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import EvaluationCase, LoRAAdapter, LoRAComposition, LoRARole, MergeMethod

_MAX_JSON_BYTES = 4 * 1024 * 1024


# {
# 責務: [_atomic_json: persist bounded JSON without exposing partial files]
# 処理: [reject symlinks and oversized payloads, then replace through a same-directory temporary file]
# 引数: [path: target JSON path, payload: JSON-compatible content]
# 戻り値: [None: complete document written]
# }
def write_json_atomic(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("JSON output cannot be a symlink")
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8")
    if len(encoded) > _MAX_JSON_BYTES:
        raise ValueError("JSON document exceeds the configured size limit")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


# {
# 責務: [composition_payload: encode a portable composition recipe]
# 処理: [serialize scales, validation cases, method and provenance without tensor data]
# 引数: [composition: recipe to encode]
# 戻り値: [dict[str, Any]: JSON-safe recipe document]
# }
def composition_payload(composition: LoRAComposition) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_loras": list(composition.source_loras),
        "base_model": composition.base_model,
        "merge_method": composition.merge_method.value,
        "global_scales": composition.global_scales,
        "layer_scales": composition.layer_scales,
        "score": composition.score,
        "validation_prompts": [asdict(case) for case in composition.validation_prompts],
        "provenance": composition.provenance,
        "created_at": composition.created_at,
        "static_merged_lora": str(composition.static_merged_lora)
        if composition.static_merged_lora
        else None,
    }


# {
# 責務: [save_composition: write the non-destructive portable runtime recipe]
# 処理: [persist one schema-versioned JSON recipe atomically]
# 引数: [composition: selected recipe, destination: output JSON path]
# 戻り値: [Path: saved recipe path]
# }
def save_composition(composition: LoRAComposition, destination: str | Path) -> Path:
    target = Path(destination).expanduser()
    write_json_atomic(target, composition_payload(composition))
    return target


# {
# 責務: [load_adapter: load one LoRA safetensors artifact with conservative metadata checks]
# 処理: [load CPU arrays through the optional safetensors package and normalize supported metadata keys]
# 引数: [path: input LoRA file, role: user-declared functional role]
# 戻り値: [LoRAAdapter: tensors, family, architecture, rank, alpha and provenance]
# }
def load_adapter(path: str | Path, role: LoRARole = LoRARole.CONCEPT) -> LoRAAdapter:
    try:
        from safetensors import safe_open
        from safetensors.numpy import load_file
    except ImportError as error:
        raise RuntimeError(
            "Install requirements-lora-composition.txt to read safetensors LoRAs"
        ) from error
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size > 16 * 1024**3:
        raise ValueError("LoRA source must be a regular file no larger than 16 GiB")
    tensors = load_file(str(source))
    with safe_open(str(source), framework="numpy") as safe_file:
        metadata = safe_file.metadata() or {}
    family = metadata.get("base_model_family", metadata.get("ss_base_model_version", "unknown"))
    architecture = metadata.get("architecture", metadata.get("modelspec.architecture", "unknown"))
    rank = int(metadata.get("ss_network_dim", metadata.get("lora_rank", "0")))
    alpha = float(metadata.get("ss_network_alpha", metadata.get("lora_alpha", str(rank))))
    if rank <= 0:
        rank = next(
            (
                int(value.shape[0])
                for key, value in tensors.items()
                if key.endswith((".lora_A.weight", ".lora_down.weight"))
            ),
            0,
        )
    provenance = {
        "source_path": str(source),
        "source_sha256": _sha256(source),
        "metadata": json.dumps(metadata, sort_keys=True, ensure_ascii=True),
    }
    if len(provenance["metadata"]) > 64 * 1024:
        raise ValueError("LoRA metadata exceeds the provenance size limit")
    return LoRAAdapter(
        source.stem,
        tensors,
        family,
        architecture,
        rank,
        alpha,
        role,
        provenance,
        metadata.get("slider_direction"),
        float(metadata.get("slider_minimum", "-1")),
        float(metadata.get("slider_maximum", "1")),
        float(metadata.get("slider_neutral", "0")),
    )


# {
# 責務: [_sha256: identify artifact bytes for reproducibility]
# 処理: [stream the source file through SHA-256 without loading it all into memory]
# 引数: [path: regular file]
# 戻り値: [str: lowercase SHA-256 digest]
# }
def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# {
# 責務: [save_merged_lora: write static merged tensors and sidecar provenance]
# 処理: [use safetensors safe serialization and refuse overwriting existing source/output files]
# 引数: [tensors: merged factors, destination: new safetensors path, metadata: provenance values]
# 戻り値: [Path: saved artifact path]
# }
def save_merged_lora(
    tensors: dict[str, np.ndarray], destination: str | Path, metadata: dict[str, str]
) -> Path:
    try:
        from safetensors.numpy import save_file
    except ImportError as error:
        raise RuntimeError(
            "Install requirements-lora-composition.txt to write safetensors LoRAs"
        ) from error
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("artifact output directory cannot be a symlink")
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing artifact: {target}")
    if not tensors or any(not np.isfinite(tensor).all() for tensor in tensors.values()):
        raise ValueError("merged LoRA tensors must be nonempty and finite")
    safe_metadata = {str(key): str(value) for key, value in metadata.items()}
    if sum(len(key) + len(value) for key, value in safe_metadata.items()) > 256 * 1024:
        raise ValueError("merged LoRA metadata exceeds the size limit")
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        save_file(tensors, str(temporary), metadata=safe_metadata)
        os.link(temporary, target)
        temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


# {
# 責務: [new_composition: build timestamped recipe with source artifact hashes]
# 処理: [record source identity, evaluation prompts, selected scales and method provenance]
# 引数: [adapters: source artifacts, base_model: target base, method: selected merge rule, global_scales: chosen scales, layer_scales: optional local scales, score: optional evaluator result, cases: fixed validation prompts, static_path: optional merged output]
# 戻り値: [LoRAComposition: immutable saved-recipe data]
# }
def new_composition(
    adapters: tuple[LoRAAdapter, ...],
    base_model: str,
    method: MergeMethod,
    global_scales: dict[str, float],
    layer_scales: dict[str, dict[str, float]] | None = None,
    score: float | None = None,
    cases: tuple[EvaluationCase, ...] = (),
    static_path: Path | None = None,
) -> LoRAComposition:
    return LoRAComposition(
        source_loras=tuple(adapter.name for adapter in adapters),
        base_model=base_model,
        merge_method=method,
        global_scales=dict(global_scales),
        layer_scales=layer_scales or {},
        score=score,
        validation_prompts=cases,
        provenance={
            "source_loras": [adapter.provenance for adapter in adapters],
            "merge_method": method.value,
        },
        created_at=datetime.now(timezone.utc).isoformat(),
        static_merged_lora=static_path,
    )
