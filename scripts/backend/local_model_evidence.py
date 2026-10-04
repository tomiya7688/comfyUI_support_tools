"""Classify a catalog entry using its configured local model file when available."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.comfyui_support_tools.shared.model_identity import (
    ModelClassification, ModelFamily, ModelKind, classify_model,
)
from src.comfyui_support_tools.shared.safetensors_metadata import (
    SafetensorsMetadataError, read_safetensors_evidence,
)


# {
# 責務: [_model_roots: 宣言されたmodel種別に対応する共有・legacy・runtime directoryを求める]
# 処理: [1: checkpoint固有rootを選ぶ, 2: 他種別はmodel rootごとに対応folderを展開する]
# 引数: [kind: 解決するmodel種別]
# 戻り値: [検索するmodel directory一覧]
# }
def _model_roots(kind: ModelKind) -> list[Path]:
    from scripts import context

    shared = [context.MODELS_DIR, context.LEGACY_MODELS_DIR]
    runtime = context.RUNTIME_DIR / "models"
    if kind is ModelKind.CHECKPOINT:
        backend_folder = "checkpoints" if context.RUNTIME_BACKEND == "comfyui" else "Stable-diffusion"
        return [context.CHECKPOINTS_DIR, *context.LEGACY_CHECKPOINTS_DIRS, runtime / backend_folder]
    folders = {
        ModelKind.UNET: ("diffusion_models", "unet"),
        ModelKind.LORA: ("Lora", "loras"),
        ModelKind.VAE: ("VAE", "vae"),
    }.get(kind, ())
    return [root / folder for root in [*shared, runtime] for folder in folders]


# {
# 責務: [_matching_files: catalog名に一致する安全なlocal model fileを探す]
# 処理: [1: checkpoint hash表記と相対pathを正規化する, 2: traversalを拒否する,
# 3: 複数rootから完全名またはLoRA stem一致を収集する]
# 引数: [name: catalog上のmodel名, kind: 検索するmodel種別]
# 戻り値: [重複pathを除いて並べた一致file一覧]
# }
def _matching_files(name: str, kind: ModelKind) -> list[Path]:
    if kind is ModelKind.CHECKPOINT:
        name = re.sub(r" \[[0-9a-fA-F]{8,64}\]$", "", name)
    relative = Path(name.replace("\\", "/"))
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        return []
    files = set()
    for root in _model_roots(kind):
        try:
            candidate = root / relative
            if candidate.is_file():
                files.add(candidate.resolve())
            # A1111 exposes LoRA stems rather than relative model filenames.
            suffixes = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
            if kind is ModelKind.LORA and relative.suffix.casefold() not in suffixes:
                candidates = (root.rglob("*") if len(relative.parts) == 1 else candidate.parent.glob("*"))
                for item in candidates:
                    if (
                        item.is_file()
                        and item.stem.casefold() == relative.name.casefold()
                        and item.suffix.casefold() in suffixes
                    ):
                        files.add(item.resolve())
        except OSError:
            continue
    return sorted(files, key=str)


# {
# 責務: [_file_classification: safetensors header evidenceからmodel familyを分類してcacheする]
# 処理: [1: header・tensor shapeを読む, 2: evidenceまたはfallback根拠でmodelを分類する]
# 引数: [path: model file path, mtime_ns: 更新検出用mtime, size: 更新検出用file size,
# kind: catalogで宣言されたmodel種別]
# 戻り値: [family・kindと判定根拠を含むclassification]
# }
@lru_cache(maxsize=128)
def _file_classification(path: str, mtime_ns: int, size: int, kind: ModelKind) -> ModelClassification:
    # Cache compact results, not large headers; the stat signature detects replacements.
    try:
        metadata, shapes = read_safetensors_evidence(path)
    except SafetensorsMetadataError as exc:
        result = classify_model(path, declared_kind=kind)
        return ModelClassification(
            result.family, result.kind,
            f"{result.family_reason} Local metadata unavailable: {exc}.", result.kind_reason,
        )
    return classify_model(path, metadata=metadata, tensor_shapes=shapes, declared_kind=kind)


# {
# 責務: [classify_local_model_choice: catalog entryをlocal model evidenceで分類する]
# 処理: [1: 対応fileを探す, 2: 多重一致やmetadata欠損を保守的に扱う,
# 3: family・kindと根拠を返す]
# 引数: [name: catalog上のmodel名, kind: catalogで宣言された種別]
# 戻り値: [local evidenceに基づくModelClassification]
# }
def classify_local_model_choice(name: str, kind: ModelKind) -> ModelClassification:
    """Use local header evidence, retaining uncertainty for duplicate filenames."""
    files = _matching_files(name, kind)
    if len(files) > 1:
        return ModelClassification(
            ModelFamily.UNKNOWN, kind,
            "Multiple distinct local files match this catalog name; model family is ambiguous.",
            f"Using declared model kind {kind.value}.",
        )
    warning = ""
    if files and files[0].suffix.casefold() == ".safetensors":
        try:
            signature = files[0].stat()
            return _file_classification(str(files[0]), signature.st_mtime_ns, signature.st_size, kind)
        except OSError as exc:
            warning = f"Local metadata unavailable: {exc}."
    result = classify_model(files[0] if files else name, declared_kind=kind)
    if not warning:
        return result
    return ModelClassification(
        result.family, result.kind, f"{result.family_reason} {warning}", result.kind_reason,
    )
