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
#   責務: [_model_roots: model kindに応じてconfigured and legacy search rootsをresolveする]
#   処理: [combine shared/runtime paths with backend catalog checkpoint directories]
#   引数: [kind]
#   戻り値: [list[Path]]
# }
def _model_roots(kind: ModelKind) -> list[Path]:
    from scripts import context

    shared = [context.MODELS_DIR, context.LEGACY_MODELS_DIR]
    runtime = context.RUNTIME_DIR / "models"
    if kind is ModelKind.CHECKPOINT:
        catalog = context.create_configured_generation_backend_catalog()
        runtime_roots = [runtime / folder for folder in catalog.runtime_checkpoint_folders]
        return [context.CHECKPOINTS_DIR, *context.LEGACY_CHECKPOINTS_DIRS, *runtime_roots]
    folders = {
        ModelKind.UNET: ("diffusion_models", "unet"),
        ModelKind.LORA: ("Lora", "loras"),
        ModelKind.VAE: ("VAE", "vae"),
    }.get(kind, ())
    return [root / folder for root in [*shared, runtime] for folder in folders]


# {
#   責務: [_matching_files: catalog model nameに一致するsafe local model filesを探す]
#   処理: [reject absolute/traversal paths, find exact files, support LoRA stems, tolerate OS errors, and sort unique matches]
#   引数: [name, kind]
#   戻り値: [list[Path]]
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
#   責務: [_file_classification: safetensors header evidenceをstat signature keyでcacheしてclassifyする]
#   処理: [read metadata/shapes, fallback to name-based classification on unavailable metadata, and retain evidence reason]
#   引数: [path, mtime_ns, size, kind]
#   戻り値: [ModelClassification]
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
#   責務: [classify_local_model_choice: local model header evidenceを使いambiguous catalog namesにはuncertaintyを保持する]
#   処理: [matching filesを解決し、duplicate時はunknown kindを返し、safetensors evidenceまたはname classificationへfallbackする]
#   引数: [name: catalog model name, kind: declared model kind]
#   戻り値: [ModelClassification: family/kind and evidence reasons]
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
