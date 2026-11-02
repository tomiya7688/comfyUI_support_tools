"""Stable contracts shared by architecture and training-tool adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


# {
# 責務: [SupportLevel: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class SupportLevel(str, Enum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


# {
# 責務: [Quantization: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class Quantization(str, Enum):
    NONE = "none"
    NF4 = "nf4"
    INT4 = "int4"
    INT8 = "int8"
    FP8 = "fp8"
    TORCHAO = "torchao"
    QUANTO = "quanto"


# {
# 責務: [AdapterMethod: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class AdapterMethod(str, Enum):
    LORA = "lora"
    LOCON = "locon"
    LOHA = "loha"
    LOKR = "lokr"
    OFT = "oft"
    BOFT = "boft"
    DORA = "dora"
    IA3 = "ia3"
    GLORA = "glora"
    DYLORA = "dylora"
    FULL = "full"
    NORM = "norm"


# {
# 責務: [ArchitectureProfile: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class ArchitectureProfile:
    """Architecture-specific latent, text, target and resource contract."""

    key: str
    family: str
    flavour: str
    text_encoder: str
    latent_format: str
    target_modules: tuple[str, ...]
    training_schedule: str
    text_encoder_trainable: bool
    minimum_vram_gib: float
    dataset_kind: str = "image_caption"
    supported_trainers: dict[str, SupportLevel] = field(default_factory=dict)
    methods: dict[str, SupportLevel] = field(default_factory=dict)
    quantization: dict[str, tuple[Quantization, ...]] = field(default_factory=dict)
    features: dict[str, tuple[str, ...]] = field(default_factory=dict)
    supported_precision: tuple[str, ...] = ("fp32", "fp16", "bf16")
    minimum_trainer_versions: dict[str, str] = field(default_factory=dict)


# {
# 責務: [TrainingSpec: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class TrainingSpec:
    """Trainer-neutral request translated only by a selected trainer adapter."""

    architecture: str
    method: AdapterMethod
    base_model: Path
    dataset: Path
    output: Path
    steps: int
    rank: int
    alpha: float
    dataset_kind: str | None = None
    target_modules: tuple[str, ...] = ()
    resolution: int = 1024
    train_text_encoder: bool = False
    precision: str = "bf16"
    quantization: Quantization = Quantization.NONE
    gradient_checkpointing: bool = True
    optimizer_offload: bool = False
    cpu_offload: bool = False
    quantized_text_encoder: bool = False
    cached_embeddings: bool = False
    vae_cache: bool = True
    lower_resolution_probe: bool = False
    batch_size: int = 1
    gradient_accumulation: int = 1
    seed: int = 1


# {
# 責務: [TrainerProbe: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class TrainerProbe:
    """Runtime identity and observed capabilities for a trainer installation."""

    trainer: str
    available: bool
    version: str | None
    executable: str | None
    reason: str
    capability_fingerprint: str


# {
# 責務: [TrainingProvenance: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class TrainingProvenance:
    """Reproducibility record for imported trainer recipes and local changes."""

    trainer: str
    trainer_version: str | None
    upstream_repository: str
    upstream_revision: str | None
    source_recipe_sha256: str
    local_changes: bool
    local_change_fingerprint: str
    capability_fingerprint: str


# {
# 責務: [MethodSupport: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class MethodSupport:
    """Architecture-specific method outcome consumed by Auto and manual choice."""

    trainer: str
    architecture: str
    method: AdapterMethod
    level: SupportLevel
    reason: str


# {
# 責務: [SupportMatrixEntry: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class SupportMatrixEntry:
    """Resolved support record for one trainer/architecture/method tuple."""

    trainer: str
    architecture: str
    version: str | None
    methods: tuple[MethodSupport, ...]
    precision: tuple[str, ...]
    quantization: tuple[Quantization, ...]
    features: tuple[str, ...]
    target_modules: tuple[str, ...]
    minimum_vram_gib: float
    capability_fingerprint: str


# {
# 責務: [TrainerResolution: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class TrainerResolution:
    """Selected trainer with explicit reason and support level."""

    selected: str | None
    method: AdapterMethod
    architecture: str
    level: SupportLevel
    reason: str


# {
# 責務: [ConfigValidation: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class ConfigValidation:
    """Trainer-neutral and trainer-specific validation findings."""

    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# {
# 責務: [SmokeTestResult: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class SmokeTestResult:
    """Bounded dry-run result that gates full training."""

    passed: bool
    trainer: str
    version: str | None
    steps: int
    checkpoint: Path | None
    sample: Path | None
    output: str
    reason: str


# {
# 責務: [TrainerAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class TrainerAdapter(Protocol):
    """Runtime contract required before one trainer can be selected."""

    # {
    # 責務: [describe: return adapter identity and supported operation surface]
    # 処理: [describe its external trainer integration without claiming runtime availability]
    # 引数: [self: adapter instance]
    # 戻り値: [dict[str, str]: stable adapter descriptor]
    # }
    def describe(self) -> dict[str, str]: ...

    # {
    # 責務: [probe: detect the installed trainer version and executable]
    # 処理: [run a bounded version probe without a shell or network access]
    # 引数: [self: adapter instance]
    # 戻り値: [TrainerProbe: installed state and capability fingerprint]
    # }
    def probe(self) -> TrainerProbe: ...

    # {
    # 責務: [version: expose the probed trainer version]
    # 処理: [reuse the current runtime probe and return a stable version identifier]
    # 引数: [self: adapter instance]
    # 戻り値: [str | None: installed version or unavailable]
    # }
    def version(self) -> str | None: ...

    # {
    # 責務: [supported_models: list profile keys with runtime support]
    # 処理: [combine profile declarations and the probed trainer version]
    # 引数: [self: adapter instance]
    # 戻り値: [tuple[str, ...]: runtime-available architecture keys]
    # }
    def supported_models(self) -> tuple[str, ...]: ...

    # {
    # 責務: [supported_methods: resolve method support for one architecture]
    # 処理: [return supported, experimental and unsupported states separately]
    # 引数: [self: adapter instance, architecture: profile key]
    # 戻り値: [tuple[MethodSupport, ...]: known method outcomes]
    # }
    def supported_methods(self, architecture: str) -> tuple[MethodSupport, ...]: ...

    # {
    # 責務: [supported_precision: report trainer/profile precision intersection]
    # 処理: [avoid collapsing trainer-specific precision into a generic boolean]
    # 引数: [self: adapter instance, architecture: profile key]
    # 戻り値: [tuple[str, ...]: supported precision names]
    # }
    def supported_precision(self, architecture: str) -> tuple[str, ...]: ...

    # {
    # 責務: [supported_quantization: report runtime quantization intersection]
    # 処理: [retain trainer-specific quantization choices and exclusions]
    # 引数: [self: adapter instance, architecture: profile key]
    # 戻り値: [tuple[Quantization, ...]: detected supported quantizers]
    # }
    def supported_quantization(self, architecture: str) -> tuple[Quantization, ...]: ...

    # {
    # 責務: [supported_features: report individual offload and caching features]
    # 処理: [retain trainer-specific strategy support rather than flattening to one low-VRAM flag]
    # 引数: [self: adapter instance, architecture: profile key]
    # 戻り値: [tuple[str, ...]: supported memory and cache strategies]
    # }
    def supported_features(self, architecture: str) -> tuple[str, ...]: ...

    # {
    # 責務: [target_modules: discover valid target names for a model]
    # 処理: [return adapter-provided targets instead of shared hard-coded presets]
    # 引数: [self: adapter instance, architecture: profile key, model_path: optional local model]
    # 戻り値: [tuple[str, ...]: verified target module candidates]
    # }
    def target_modules(
        self, architecture: str, model_path: Path | None = None
    ) -> tuple[str, ...]: ...

    # {
    # 責務: [validate_config: validate a neutral spec against the adapter]
    # 処理: [check model, method, modules, precision, quantization and resource constraints]
    # 引数: [self: adapter instance, spec: common training specification]
    # 戻り値: [ConfigValidation: errors and experimental warnings]
    # }
    def validate_config(self, spec: TrainingSpec) -> ConfigValidation: ...

    # {
    # 責務: [translate_config: translate a common spec into native trainer configuration]
    # 処理: [map neutral fields to a JSON, YAML-compatible or CLI/TOML representation]
    # 引数: [self: adapter instance, spec: common training specification]
    # 戻り値: [dict[str, object]: trainer-native configuration]
    # }
    def translate_config(self, spec: TrainingSpec) -> dict[str, object]: ...

    # {
    # 責務: [smoke_command: build an explicitly declared short training command]
    # 処理: [expand only known config, step and output placeholders without shell parsing]
    # 引数: [self: adapter instance, config_path: generated config, steps: bounded smoke steps, output: temporary destination]
    # 戻り値: [tuple[str, ...] | None: validated argv or unavailable]
    # }
    def smoke_command(
        self, config_path: Path, steps: int, output: Path
    ) -> tuple[str, ...] | None: ...
