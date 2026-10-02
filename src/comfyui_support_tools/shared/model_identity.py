"""Conservative model-family and model-kind inference."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ModelFamily(str, Enum):
    SD_1_5 = "sd1.5"
    SDXL = "sdxl"
    FLUX = "flux"
    ANIMA = "anima"
    UNKNOWN = "unknown"


class ModelKind(str, Enum):
    CHECKPOINT = "checkpoint"
    UNET = "unet"
    LORA = "lora"
    VAE = "vae"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModelClassification:
    family: ModelFamily
    kind: ModelKind
    family_reason: str
    kind_reason: str


_FAMILY_PATTERNS = {
    ModelFamily.SD_1_5: re.compile(
        r"(?<![a-z0-9])(?:sd[\s_.-]*v?1[\s_.-]*5|stable[\s_.-]*diffusion[\s_.-]*v?1[\s_.-]*5)(?![a-z0-9])",
        re.IGNORECASE,
    ),
    ModelFamily.SDXL: re.compile(
        r"(?<![a-z0-9])(?:sd[\s_.-]*xl|stable[\s_.-]*diffusion[\s_.-]*xl)(?![a-z0-9])"
        r"|(?<![a-z0-9])(?:animagine|illustrious|juggernaut|noobai|pony|realvis)[\s_.-]*xl(?![a-z0-9])",
        re.IGNORECASE,
    ),
    ModelFamily.FLUX: re.compile(r"(?<![a-z0-9])flux(?:[\s_.-]*1)?(?![a-z0-9])", re.IGNORECASE),
    ModelFamily.ANIMA: re.compile(r"(?<![a-z0-9])anima(?![a-z0-9])", re.IGNORECASE),
}

_FAMILY_METADATA_KEYS = {
    "modelspec.architecture", "modelspec.title", "ss_base_model_version",
    "ss_sd_model_name", "ss_model_name", "base_model", "model_type", "architecture",
}
_KIND_DIRECTORY_NAMES = {
    "checkpoint": ModelKind.CHECKPOINT, "checkpoints": ModelKind.CHECKPOINT,
    "unet": ModelKind.UNET, "unets": ModelKind.UNET, "diffusion_models": ModelKind.UNET,
    "lora": ModelKind.LORA, "loras": ModelKind.LORA,
    "vae": ModelKind.VAE, "vaes": ModelKind.VAE,
}


def _path_parts(model_path: str | Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in str(model_path).replace("\\", "/").split("/") if part)


def _family_candidates(value: str) -> set[ModelFamily]:
    return {family for family, pattern in _FAMILY_PATTERNS.items() if pattern.search(value)}


def _metadata_signals(metadata: Mapping[str, str] | None) -> list[tuple[ModelFamily, str]]:
    if not metadata:
        return []
    signals = []
    for key, value in metadata.items():
        if isinstance(key, str) and isinstance(value, str) and key.casefold() in _FAMILY_METADATA_KEYS:
            signals.extend((family, f"metadata {key}={value!r}") for family in _family_candidates(value))
    return signals


def _path_signals(model_path: str | Path) -> list[tuple[ModelFamily, str]]:
    return [
        (family, f"path component {part!r}")
        for part in _path_parts(model_path)
        for family in _family_candidates(part)
    ]


def _infer_family(model_path: str | Path, metadata: Mapping[str, str] | None) -> tuple[ModelFamily, str]:
    signals = _metadata_signals(metadata) + _path_signals(model_path)
    families = {family for family, _ in signals}
    if len(families) > 1:
        details = ", ".join(f"{family.value} from {source}" for family, source in signals)
        return ModelFamily.UNKNOWN, f"Conflicting family signals: {details}."
    if not signals:
        return ModelFamily.UNKNOWN, "No recognized family marker in the model path or metadata."
    family = signals[0][0]
    sources = ", ".join(dict.fromkeys(source for _, source in signals))
    return family, f"Inferred {family.value} from {sources}."


def _infer_kind(model_path: str | Path, declared_kind: ModelKind | str | None) -> tuple[ModelKind, str]:
    if declared_kind is not None:
        try:
            kind = declared_kind if isinstance(declared_kind, ModelKind) else ModelKind(declared_kind.casefold())
        except (AttributeError, ValueError):
            kind = ModelKind.UNKNOWN
        if kind is not ModelKind.UNKNOWN:
            return kind, f"Using declared model kind {kind.value}."

    matches = {
        _KIND_DIRECTORY_NAMES[part]
        for part in _path_parts(model_path)[:-1]
        if part in _KIND_DIRECTORY_NAMES
    }
    if len(matches) == 1:
        kind = next(iter(matches))
        return kind, f"Inferred {kind.value} from a model directory name."
    if len(matches) > 1:
        names = ", ".join(sorted(kind.value for kind in matches))
        return ModelKind.UNKNOWN, f"Conflicting model directory kinds: {names}."
    return ModelKind.UNKNOWN, "No declared kind or recognized model directory name."


def classify_model(
    model_path: str | Path,
    *,
    metadata: Mapping[str, str] | None = None,
    declared_kind: ModelKind | str | None = None,
) -> ModelClassification:
    """Infer a model family and kind, preserving uncertainty in the result."""
    family, family_reason = _infer_family(model_path, metadata)
    kind, kind_reason = _infer_kind(model_path, declared_kind)
    return ModelClassification(family, kind, family_reason, kind_reason)
