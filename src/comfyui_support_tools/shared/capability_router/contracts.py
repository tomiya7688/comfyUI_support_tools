"""Typed model, license, task and resource metadata for capability routing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


# {
#   責務: [GenerationUseCase: image generationのapplication intentを列挙する]
#   フィールド: [GENERAL, PHOTOREALISTIC, ANIME, ILLUSTRATION, CHARACTER, LANDSCAPE, PRODUCT, OBJECT_ASSET, TYPOGRAPHY, TRANSPARENT_ASSET, CONCEPT_ART, FAST_DRAFT, HIGH_QUALITY, LOW_VRAM, LORA_CENTRIC]
#   許可値: [general, photo, anime, character, landscape, product, object, typography, transparent, concept, fast, quality, low_vram, lora]
# }
class GenerationUseCase(str, Enum):
    GENERAL = "general"
    PHOTOREALISTIC = "photorealistic"
    ANIME = "anime"
    ILLUSTRATION = "illustration"
    CHARACTER = "character"
    LANDSCAPE = "landscape"
    PRODUCT = "product"
    OBJECT_ASSET = "object_asset"
    TYPOGRAPHY = "typography"
    TRANSPARENT_ASSET = "transparent_asset"
    CONCEPT_ART = "concept_art"
    FAST_DRAFT = "fast_draft"
    HIGH_QUALITY = "high_quality"
    LOW_VRAM = "low_vram"
    LORA_CENTRIC = "lora_centric"


# {
#   責務: [CapabilityFeature: model/workflowが明示的に提供するgeneration capabilityを表す]
#   フィールド: [TXT2IMG, IMG2IMG, NATURAL_LANGUAGE, TAG_PROMPT, PROMPT_REWRITE, TYPOGRAPHY, PHOTOREALISM, ANIME, ILLUSTRATION, PRODUCT, CHARACTER, LANDSCAPE, TRANSPARENT_RGBA, REFERENCE_IMAGES, LAYOUT/POSE/DEPTH CONTROL, CONTROLNET, LORA, LORA_FINETUNE]
# }
class CapabilityFeature(str, Enum):
    TXT2IMG = "txt2img"
    IMG2IMG = "img2img"
    NATURAL_LANGUAGE = "natural_language"
    TAG_PROMPT = "tag_prompt"
    PROMPT_REWRITE = "prompt_rewrite"
    TYPOGRAPHY = "typography"
    PHOTOREALISM = "photorealism"
    ANIME = "anime"
    ILLUSTRATION = "illustration"
    PRODUCT = "product"
    CHARACTER = "character"
    LANDSCAPE = "landscape"
    TRANSPARENT_RGBA = "transparent_rgba"
    REFERENCE_IMAGES = "reference_images"
    LAYOUT_CONTROL = "layout_control"
    POSE_CONTROL = "pose_control"
    DEPTH_CONTROL = "depth_control"
    CONTROLNET = "controlnet"
    LORA = "lora"
    LORA_FINETUNE = "lora_finetune"


# {
#   責務: [ModelLifecycle: capability descriptorの導入・推奨状態を表す]
#   フィールド: [DISCOVERED, SUPPORTED, EXPERIMENTAL, RECOMMENDED, LEGACY, UNAVAILABLE]
# }
class ModelLifecycle(str, Enum):
    DISCOVERED = "discovered"
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    RECOMMENDED = "recommended"
    LEGACY = "legacy"
    UNAVAILABLE = "unavailable"


# {
#   責務: [LatencyClass: modelの定性的なlatency tierを表す]
#   フィールド: [VERY_FAST, FAST, MEDIUM, SLOW, UNKNOWN]
# }
class LatencyClass(str, Enum):
    VERY_FAST = "very_fast"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    UNKNOWN = "unknown"


# {
#   責務: [QualityClass: modelの定性的なquality tier metadataを表す]
#   フィールド: [DRAFT, BALANCED, HIGH, UNKNOWN]
#   注意: [classはmeasured per-task scoreではなくbenchmarkなしに順位付けへ使用しない]
# }
class QualityClass(str, Enum):
    DRAFT = "draft"
    BALANCED = "balanced"
    HIGH = "high"
    UNKNOWN = "unknown"


# {
#   責務: [LicenseEvidence: source, license identifierとcommercial evidenceを保持する]
#   フィールド: [license_id, commercial_use, reference, verified]
# }
@dataclass(frozen=True, slots=True)
class LicenseEvidence:
    license_id: str
    commercial_use: bool | None
    reference: str = ""
    verified: bool = False

    # {
    #   責務: [__post_init__: license claimとsource URLの形式をvalidateする]
    #   処理: [require a license identifier and HTTP(S) provenance when provided]
    #   引数: [self: explicit license evidence]
    #   戻り値: []
    #   エラー: [ValueError: missing identifier or malformed reference]
    # }
    def __post_init__(self) -> None:
        if not self.license_id.strip():
            raise ValueError("license identifier must be explicit, use 'unknown' when unavailable")
        if self.reference and not self.reference.startswith(("https://", "http://")):
            raise ValueError("license reference must be an HTTP(S) URL")


# {
#   責務: [GenerationCapability: installed model/workflowのrouting metadataを宣言する]
#   フィールド: [profile/family/aliases/backend/capabilities/use cases/prompt+workflow policy/resource/license/lifecycle/locality]
#   処理: [unknown metadataはNone/unknownのまま保ち, automatic selectionに必要なevidenceを公開する]
# }
@dataclass(frozen=True, slots=True)
class GenerationCapability:
    profile_id: str
    family: str
    aliases: tuple[str, ...]
    backend: str
    features: frozenset[CapabilityFeature]
    recommended_use_cases: frozenset[GenerationUseCase]
    prompt_policy_id: str
    workflow_profile_id: str | None
    minimum_vram_gib: float | None
    minimum_ram_gib: float | None
    recommended_steps: int | None
    quantized_vram_gib: tuple[tuple[str, float], ...]
    maximum_resolution: tuple[int, int] | None
    latency_class: LatencyClass
    quality_class: QualityClass
    license: LicenseEvidence
    lifecycle: ModelLifecycle = ModelLifecycle.SUPPORTED
    lora_families: frozenset[str] = frozenset()
    supported_controls: frozenset[str] = frozenset()
    local_only: bool = True
    evidence_reference: str = ""

    # {
    #   責務: [__post_init__: capability metadataが矛盾した数値や未宣言値を持たないことを確認する]
    #   処理: [validate resource, feature, workflow, license and evidence declarations]
    #   引数: [self: immutable model capability]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: malformed capability descriptor]
    # }
    def __post_init__(self) -> None:
        if not all((self.profile_id.strip(), self.family.strip(), self.backend.strip())):
            raise ValueError("capability ID, family and backend must not be empty")
        if not self.aliases or any(not alias.strip() for alias in self.aliases):
            raise ValueError("capabilities require non-empty installed model aliases")
        if not self.features or CapabilityFeature.TXT2IMG not in self.features:
            raise ValueError("a text-to-image capability must explicitly declare txt2img")
        if not self.recommended_use_cases:
            raise ValueError("capabilities require at least one recommended use case")
        if self.minimum_vram_gib is not None and (
            isinstance(self.minimum_vram_gib, bool)
            or not math.isfinite(self.minimum_vram_gib)
            or self.minimum_vram_gib <= 0
        ):
            raise ValueError("minimum VRAM must be a positive finite number or unknown")
        if self.minimum_ram_gib is not None and (
            isinstance(self.minimum_ram_gib, bool)
            or not math.isfinite(self.minimum_ram_gib)
            or self.minimum_ram_gib <= 0
        ):
            raise ValueError("minimum RAM must be a positive finite number or unknown")
        quantization_names = [name for name, _value in self.quantized_vram_gib]
        if len(quantization_names) != len(set(quantization_names)) or any(
            not name.strip() or isinstance(value, bool) or not math.isfinite(value) or value <= 0
            for name, value in self.quantized_vram_gib
        ):
            raise ValueError(
                "quantized VRAM requirements must use unique names and positive values"
            )
        if self.maximum_resolution is not None and any(
            isinstance(value, bool) or value < 64 for value in self.maximum_resolution
        ):
            raise ValueError("maximum resolution dimensions must be at least 64 pixels")
        if self.maximum_resolution is not None and len(self.maximum_resolution) != 2:
            raise ValueError("maximum resolution must contain width and height")
        if self.recommended_steps is not None and (
            isinstance(self.recommended_steps, bool) or self.recommended_steps <= 0
        ):
            raise ValueError("recommended steps must be a positive integer")
        if self.evidence_reference and not self.evidence_reference.startswith(
            ("https://", "http://")
        ):
            raise ValueError("capability evidence reference must be an HTTP(S) URL")


# {
#   責務: [GenerationIntent: routing constraintsとuser preferenceをまとめる]
#   フィールド: [use_case, backend, memory, quality/latency, license/offline, LoRA/control, transparency/text, resolution, count, override]
# }
@dataclass(frozen=True, slots=True)
class GenerationIntent:
    use_case: GenerationUseCase
    backend: str
    installed_models: tuple[str, ...]
    available_workflows: tuple[str, ...] = ()
    available_vram_gib: float | None = None
    available_ram_gib: float | None = None
    quality_preference: QualityClass = QualityClass.UNKNOWN
    latency_preference: LatencyClass = LatencyClass.UNKNOWN
    commercial_required: bool = False
    offline_required: bool = False
    required_lora_family: str | None = None
    required_controls: frozenset[str] = frozenset()
    transparency_required: bool = False
    text_rendering_required: bool = False
    resolution: tuple[int, int] | None = None
    candidate_count: int = 1
    manual_model: str | None = None
    allow_unverified_resource: bool = False

    # {
    #   責務: [__post_init__: generation intentのresource and selection constraintsをvalidateする]
    #   処理: [validate immutable model/workflow inputs and positive resource limits]
    #   引数: [self: caller routing intent]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: malformed intent]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.use_case, GenerationUseCase):
            raise TypeError("use_case must use the declared GenerationUseCase enum")
        if not self.backend.strip():
            raise ValueError("backend must not be empty")
        if isinstance(self.candidate_count, bool) or not 1 <= self.candidate_count <= 100:
            raise ValueError("candidate_count must be between 1 and 100")
        if any(not isinstance(model, str) or not model.strip() for model in self.installed_models):
            raise ValueError("installed model identifiers must be non-empty strings")
        if any(
            not isinstance(workflow, str) or not workflow.strip()
            for workflow in self.available_workflows
        ):
            raise ValueError("available workflow identifiers must be non-empty strings")
        for value in (self.available_vram_gib, self.available_ram_gib):
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value <= 0
            ):
                raise ValueError("available resource values must be positive finite numbers")
        if self.resolution is not None and any(
            isinstance(value, bool) or value < 64 for value in self.resolution
        ):
            raise ValueError("requested resolution dimensions must be at least 64 pixels")
        if self.resolution is not None and len(self.resolution) != 2:
            raise ValueError("requested resolution must contain width and height")


# {
#   責務: [CapabilityRoute: selected capability, fallback chain, exclusions and decision reasonを返す]
#   フィールド: [selected_model, capability, candidates, evaluator_id, reason, excluded]
# }
@dataclass(frozen=True, slots=True)
class CapabilityRoute:
    selected_model: str
    capability: GenerationCapability
    candidates: tuple[tuple[str, GenerationCapability], ...]
    evaluator_id: str | None
    reason: str
    excluded: tuple[tuple[str, str], ...] = ()
