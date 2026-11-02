"""Conservative model-family and model-kind inference."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .tensor_model_signals import tensor_family_signals


# {
# 責務: [ModelFamily: 実装が認識するmodel architecture family]
# フィールド: [SD 1.5, SDXL, FLUX, ANIMA, UNKNOWN]
# }
class ModelFamily(str, Enum):
    SD_1_5 = "sd1.5"
    SDXL = "sdxl"
    FLUX = "flux"
    ANIMA = "anima"
    UNKNOWN = "unknown"


# {
# 責務: [ModelKind: pathまたは宣言から分類するmodel artifact種別]
# フィールド: [checkpoint, UNET, LoRA, VAE, UNKNOWN]
# }
class ModelKind(str, Enum):
    CHECKPOINT = "checkpoint"
    UNET = "unet"
    LORA = "lora"
    VAE = "vae"
    UNKNOWN = "unknown"


# {
# 責務: [ModelClassification: family/kindの推定値と各根拠を保持する]
# フィールド: [family, kind, family_reason, kind_reason]
# }
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
    "modelspec.architecture",
    "modelspec.title",
    "ss_base_model_version",
    "ss_sd_model_name",
    "ss_model_name",
    "base_model",
    "model_type",
    "architecture",
}
_KIND_DIRECTORY_NAMES = {
    "checkpoint": ModelKind.CHECKPOINT,
    "checkpoints": ModelKind.CHECKPOINT,
    "unet": ModelKind.UNET,
    "unets": ModelKind.UNET,
    "diffusion_models": ModelKind.UNET,
    "lora": ModelKind.LORA,
    "loras": ModelKind.LORA,
    "vae": ModelKind.VAE,
    "vaes": ModelKind.VAE,
}


# {
#   責務: [ _path_parts: model path文字列をslash区切りのcasefold済み要素へ分割する]
#   処理: [Windows separatorをslashにし、空要素を除いてcasefoldする]
#   引数: [model_path: filesystem pathまたはpath文字列]
#   戻り値: [parts: 正規化されたpath component tuple]
# }
def _path_parts(model_path: str | Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in str(model_path).replace("\\", "/").split("/") if part)


# {
#   責務: [_family_candidates: 文字列に含まれる認識済みfamily markerを抽出する]
#   処理: [各familyのregex patternを検索する]
#   引数: [value: path componentまたはmetadata value]
#   戻り値: [families: 一致したModelFamilyのset]
# }
def _family_candidates(value: str) -> set[ModelFamily]:
    return {family for family, pattern in _FAMILY_PATTERNS.items() if pattern.search(value)}


# {
#   責務: [_metadata_signals: 認識対象metadata keyからfamily evidenceを作る]
#   処理: [文字列key/valueかつ許可keyの値だけfamily markerを検索する]
#   引数: [metadata: model metadata mappingまたはNone]
#   戻り値: [signals: familyと出典を組にしたlist]
# }
def _metadata_signals(metadata: Mapping[str, str] | None) -> list[tuple[ModelFamily, str]]:
    if not metadata:
        return []
    signals = []
    for key, value in metadata.items():
        if (
            isinstance(key, str)
            and isinstance(value, str)
            and key.casefold() in _FAMILY_METADATA_KEYS
        ):
            signals.extend(
                (family, f"metadata {key}={value!r}") for family in _family_candidates(value)
            )
    return signals


# {
#   責務: [_path_signals: 各path componentにあるfamily markerをevidence化する]
#   処理: [正規化componentをfamily patternに照合する]
#   引数: [model_path: filesystem pathまたはpath文字列]
#   戻り値: [signals: familyと一致componentを組にしたlist]
# }
def _path_signals(model_path: str | Path) -> list[tuple[ModelFamily, str]]:
    return [
        (family, f"path component {part!r}")
        for part in _path_parts(model_path)
        for family in _family_candidates(part)
    ]


# {
#   責務: [_infer_family: path/metadata/tensor shapesのfamily evidenceを統合する]
#   処理: [複数familyはconflict、証拠なしはunknown、一意の認識familyは根拠付きで返す]
#   引数: [model_path: path, metadata: optional string metadata, tensor_shapes: optional tensor shape map]
#   戻り値: [familyと説明用reasonのtuple]
# }
def _infer_family(
    model_path: str | Path,
    metadata: Mapping[str, str] | None,
    tensor_shapes: Mapping[str, Sequence[int]] | None,
) -> tuple[ModelFamily, str]:
    signals = _metadata_signals(metadata) + _path_signals(model_path)
    signals.extend(
        (ModelFamily(family), reason) for family, reason in tensor_family_signals(tensor_shapes)
    )
    families = {family for family, _ in signals}
    if len(families) > 1:
        details = ", ".join(f"{family.value} from {source}" for family, source in signals)
        return ModelFamily.UNKNOWN, f"Conflicting family signals: {details}."
    if not signals:
        return (
            ModelFamily.UNKNOWN,
            "No recognized family marker in the model path, metadata, or tensor layout.",
        )
    if families == {ModelFamily.UNKNOWN}:
        return ModelFamily.UNKNOWN, " ".join(reason for _, reason in signals)
    family = signals[0][0]
    sources = ", ".join(dict.fromkeys(source.rstrip(".") for _, source in signals))
    return family, f"Inferred {family.value} from {sources}."


# {
#   責務: [_infer_kind: declared kindを優先し、なければmodel directory名から種別を推定する]
#   処理: [無効な宣言は無視し、複数directory kindはunknownとして返す]
#   引数: [model_path: model path, declared_kind: optional enum/string kind]
#   戻り値: [kindと説明用reasonのtuple]
# }
def _infer_kind(
    model_path: str | Path, declared_kind: ModelKind | str | None
) -> tuple[ModelKind, str]:
    if declared_kind is not None:
        try:
            kind = (
                declared_kind
                if isinstance(declared_kind, ModelKind)
                else ModelKind(declared_kind.casefold())
            )
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


# {
#   責務: [classify_model: model pathとoptional evidenceからfamily/kindを推定する]
#   処理: [_infer_familyと_infer_kindを独立に実行し、unknownを含む根拠をclassificationへ保持する]
#   引数: [model_path: path, metadata: optional metadata, tensor_shapes: optional shapes, declared_kind: optional kind]
#   戻り値: [ModelClassification: 推定値とfamily/kindの理由]
# }
def classify_model(
    model_path: str | Path,
    *,
    metadata: Mapping[str, str] | None = None,
    tensor_shapes: Mapping[str, Sequence[int]] | None = None,
    declared_kind: ModelKind | str | None = None,
) -> ModelClassification:
    """Infer a model family and kind, preserving uncertainty in the result."""
    family, family_reason = _infer_family(model_path, metadata, tensor_shapes)
    kind, kind_reason = _infer_kind(model_path, declared_kind)
    return ModelClassification(family, kind, family_reason, kind_reason)
