"""Typed contracts for resource-aware draft generation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


# {
#   責務: [GenerationIntent: fast generatorが選択できる生成用途を表す]
#   フィールド: [preview, iteration, batch_draft, background]
#   許可値: [preview, iteration, batch_draft, background]
# }
class GenerationIntent(str, Enum):
    PREVIEW = "preview"
    ITERATION = "iteration"
    BATCH_DRAFT = "batch_draft"
    BACKGROUND = "background"


# {
#   責務: [GenerationMode: 品質と速度の利用者優先度を表す]
#   フィールド: [quality, balanced, fast]
#   許可値: [quality, balanced, fast]
# }
class GenerationMode(str, Enum):
    QUALITY = "quality"
    BALANCED = "balanced"
    FAST = "fast"


# {
#   責務: [Quantization: model profileで明示できるprecision variantを制約する]
#   フィールド: [fp16, bf16, fp8, int8, int4]
#   許可値: [fp16, bf16, fp8, int8, int4]
# }
class Quantization(str, Enum):
    FP16 = "fp16"
    BF16 = "bf16"
    FP8 = "fp8"
    INT8 = "int8"
    INT4 = "int4"


# {
#   責務: [ModelCapability: efficient model profileが公開するtask capabilityを列挙する]
#   フィールド: [txt2img, img2img, lora_finetune]
#   許可値: [txt2img, img2img, lora_finetune]
# }
class ModelCapability(str, Enum):
    TXT2IMG = "txt2img"
    IMG2IMG = "img2img"
    LORA_FINETUNE = "lora_finetune"


# {
#   責務: [RuntimeResources: 実行環境から観測できた資源とbackend情報を保持する]
#   フィールド: [total/free GPU VRAM, total/free system RAM, backend, CUDA/device, precision support, CPU offload]
#   処理: [未知の測定値をNoneのまま保持し, 推測値を事実として扱わない]
# }
@dataclass(frozen=True, slots=True)
class RuntimeResources:
    gpu_vram_gib: float | None
    system_ram_gib: float | None
    backend: str
    available_vram_gib: float | None = None
    available_ram_gib: float | None = None
    cuda_available: bool | None = None
    cuda_version: str | None = None
    device_name: str | None = None
    quantizations: frozenset[Quantization] = frozenset()
    cpu_offload: bool = False

    # {
    #   責務: [__post_init__: positive known resourcesとdeclared quantizationを検証する]
    #   処理: [memory values, backend, and quantization setをvalidateする]
    #   引数: [self: immutable runtime snapshot]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        for name, value in (
            ("gpu_vram_gib", self.gpu_vram_gib),
            ("system_ram_gib", self.system_ram_gib),
            ("available_vram_gib", self.available_vram_gib),
            ("available_ram_gib", self.available_ram_gib),
        ):
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"{name} must be positive when known")
        if not self.backend.strip():
            raise ValueError("runtime backend must not be empty")
        if not isinstance(self.quantizations, frozenset) or any(
            not isinstance(value, Quantization) for value in self.quantizations
        ):
            raise TypeError("runtime quantizations must use declared values")


# {
#   責務: [FastModelProfile: model variantの必要資源と対応用途を宣言する]
#   フィールド: [id, aliases, total/precision-specific VRAM minimum, RAM minimum, intents, quantizations, capabilities, steps, backend, experimental, fast_route]
#   処理: [測定品質を含めず, 互換性と要件だけをデータとして登録する]
# }
@dataclass(frozen=True, slots=True)
class FastModelProfile:
    profile_id: str
    aliases: tuple[str, ...]
    minimum_vram_gib: float
    minimum_ram_gib: float
    intents: frozenset[GenerationIntent]
    quantizations: frozenset[Quantization]
    steps: int
    backend: str = "comfyui"
    experimental: bool = False
    capabilities: frozenset[ModelCapability] = frozenset({ModelCapability.TXT2IMG})
    fast_route: bool = True
    minimum_vram_by_quantization: tuple[tuple[Quantization, float], ...] = ()

    # {
    #   責務: [__post_init__: model profile declarationsをvalidateする]
    #   処理: [resource requirements, task capabilities, and precision thresholdsを検証する]
    #   引数: [self: immutable model profile]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.aliases:
            raise ValueError("fast model profiles require an ID and aliases")
        if (
            not math.isfinite(self.minimum_vram_gib)
            or not math.isfinite(self.minimum_ram_gib)
            or self.minimum_vram_gib <= 0
            or self.minimum_ram_gib <= 0
            or isinstance(self.steps, bool)
            or self.steps <= 0
        ):
            raise ValueError("fast model resource requirements and steps must be positive")
        if not self.intents:
            raise ValueError("fast model profiles must declare at least one supported intent")
        if not self.backend.strip():
            raise ValueError("fast model profile backend must not be empty")
        if not self.capabilities or any(
            not isinstance(value, ModelCapability) for value in self.capabilities
        ):
            raise ValueError("model profiles require declared task capabilities")
        quantization_keys = [item[0] for item in self.minimum_vram_by_quantization]
        if len(quantization_keys) != len(set(quantization_keys)) or any(
            not isinstance(quantization, Quantization)
            or isinstance(required_vram, bool)
            or not math.isfinite(required_vram)
            or required_vram <= 0
            for quantization, required_vram in self.minimum_vram_by_quantization
        ):
            raise ValueError("per-precision VRAM requirements must be unique positive values")


# {
#   責務: [FastRouteRequest: 利用可能modelと資源に基づくrouting要求を表す]
#   フィールド: [available_models, resources, intent, mode, explicit_model]
# }
@dataclass(frozen=True, slots=True)
class FastRouteRequest:
    available_models: tuple[str, ...]
    resources: RuntimeResources
    intent: GenerationIntent = GenerationIntent.PREVIEW
    mode: GenerationMode = GenerationMode.FAST
    explicit_model: str | None = None

    # {
    #   責務: [__post_init__: invalid model names and routing enum valuesを拒否する]
    #   引数: [self: immutable routing request]
    #   戻り値: []
    #   エラー: [TypeError: resource or enum type mismatch, ValueError: empty model identifier]
    # }
    # {
    #   責務: [__post_init__: routing request fieldsをvalidateする]
    #   処理: [resource snapshot, model identifiers, and enum valuesを検証する]
    #   引数: [self: immutable route request]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.resources, RuntimeResources):
            raise TypeError("route request requires a RuntimeResources snapshot")
        if not isinstance(self.available_models, tuple):
            raise TypeError("available model identifiers must be an immutable tuple")
        if not isinstance(self.intent, GenerationIntent) or not isinstance(
            self.mode, GenerationMode
        ):
            raise TypeError("route intent and mode must use declared enums")
        if any(not isinstance(name, str) or not name.strip() for name in self.available_models):
            raise ValueError("available model identifiers must be non-empty strings")
        if self.explicit_model is not None and (
            not isinstance(self.explicit_model, str) or not self.explicit_model.strip()
        ):
            raise ValueError("explicit model identifier must not be empty")


# {
#   責務: [FastRouteResult: 選択modelと適用条件の説明を保持する]
#   フィールド: [model, profile, quantization, reason]
# }
@dataclass(frozen=True, slots=True)
class FastRouteResult:
    model: str
    profile: FastModelProfile
    quantization: Quantization | None
    reason: str
