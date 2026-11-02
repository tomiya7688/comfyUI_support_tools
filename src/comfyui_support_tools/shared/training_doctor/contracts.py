"""Trainer-neutral contracts for checkpoint quality diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# {
# 責務: [ValidationTask: classify a fixed personalization prompt matrix]
# フィールド: [enum members: character, style, object and multi-concept task kinds]
# 処理: [provide stable serialized task identifiers]
# }
class ValidationTask(str, Enum):
    CHARACTER = "character"
    STYLE = "style"
    OBJECT = "object"
    MULTI_CONCEPT = "multi_concept"


# {
# 責務: [ScorePreset: identify a built-in checkpoint scoring priority]
# フィールド: [BALANCED, FIDELITY]
# 処理: [provide stable score profile identifiers]
# }
class ScorePreset(str, Enum):
    BALANCED = "balanced"
    FIDELITY = "fidelity"


# {
# 責務: [PromptScenario: describe a fixed prompt and its trigger expectation]
# フィールド: [key, prompt, trigger_present, concept_labels]
# 処理: [reject empty identifiers or prompt text]
# 引数: [key: stable case identity, prompt: fixed positive prompt, trigger_present: trigger policy, concept_labels: expected concepts]
# 戻り値: [None: validated immutable scenario]
# }
@dataclass(frozen=True)
class PromptScenario:
    key: str
    prompt: str
    trigger_present: bool
    concept_labels: tuple[str, ...] = ()
    trigger_variant: str = ""

    # {
    # 責務: [PromptScenario.__post_init__: validate the declared immutable contract]
    # 処理: [1: reject empty scenario identifiers and prompt text]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.prompt.strip():
            raise ValueError("validation scenarios need a key and prompt")


# {
# 責務: [FixedConditions: define identical generation settings for checkpoint comparisons]
# フィールド: [sampler, inference_steps, inference_step_sweep, resolutions, seeds]
# 処理: [validate bounded inference configurations and stable seed sets]
# 引数: [sampler: sampler name, inference_steps: sampling steps, resolutions: width/height pairs, seeds: fixed random seeds]
# 戻り値: [None: validated immutable conditions]
# }
@dataclass(frozen=True)
class FixedConditions:
    sampler: str = "euler"
    inference_steps: int = 28
    inference_step_sweep: tuple[int, ...] = ()
    resolutions: tuple[tuple[int, int], ...] = ((1024, 1024),)
    seeds: tuple[int, ...] = (17, 29, 43)

    # {
    # 責務: [FixedConditions.__post_init__: validate the declared immutable contract]
    # 処理: [1: validate sampler, resolutions and deterministic seed limits]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        if not self.sampler.strip() or self.inference_steps < 1:
            raise ValueError("sampler and inference steps must be valid")
        if len(self.inference_step_values) > 8:
            raise ValueError("fixed inference-step sweep must contain at most eight values")
        if not self.seeds or len(self.seeds) > 32 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("fixed validation seeds must be unique and contain 1..32 values")
        if not self.resolutions or len(self.resolutions) > 8:
            raise ValueError("fixed validation resolutions must contain 1..8 values")
        if any(
            width < 64 or height < 64 or width > 4096 or height > 4096
            for width, height in self.resolutions
        ):
            raise ValueError("validation resolution dimensions must be in 64..4096")

    # {
    # 責務: [inference_step_values: resolve the configured inference-step sweep]
    # 処理: [use explicit sweep values or fall back to the single default step count]
    # 引数: [self: fixed generation conditions]
    # 戻り値: [tuple[int, ...]: unique positive inference-step variants]
    # }
    @property
    def inference_step_values(self) -> tuple[int, ...]:
        values = self.inference_step_sweep or (self.inference_steps,)
        if any(value < 1 for value in values) or len(set(values)) != len(values):
            raise ValueError("inference-step sweep values must be unique and positive")
        return values


# {
# 責務: [ValidationPlan: bind a fixed scenario matrix to deterministic render conditions]
# フィールド: [task, scenarios, conditions, trigger, recommended_tags]
# 処理: [ensure all prompt case keys are unique and trigger text is explicit]
# 引数: [task: personalization type, scenarios: fixed prompt rows, conditions: fixed render settings, trigger: training token, recommended_tags: optional prompt additions]
# 戻り値: [None: validated immutable plan]
# }
@dataclass(frozen=True)
class ValidationPlan:
    task: ValidationTask
    scenarios: tuple[PromptScenario, ...]
    conditions: FixedConditions = FixedConditions()
    trigger: str = "<trigger>"
    recommended_tags: tuple[str, ...] = ()
    trigger_candidates: tuple[str, ...] = ()

    # {
    # 責務: [ValidationPlan.__post_init__: validate the declared immutable contract]
    # 処理: [1: require unique cases and valid trigger sweep candidates]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        keys = [scenario.key for scenario in self.scenarios]
        if not self.scenarios or len(keys) != len(set(keys)):
            raise ValueError("validation plan must have unique prompt scenario keys")
        if not any(item.trigger_present for item in self.scenarios) or all(
            item.trigger_present for item in self.scenarios
        ):
            raise ValueError("validation plan must include triggered and trigger-absent scenarios")
        if not self.trigger.strip():
            raise ValueError("training trigger must not be empty")
        candidates = self.trigger_candidates or (self.trigger,)
        if len(candidates) > 8 or any(not value.strip() for value in candidates):
            raise ValueError("trigger sweep must contain 1..8 nonempty candidates")
        if len({value.casefold() for value in candidates}) != len(candidates):
            raise ValueError("trigger candidates must be unique")


# {
# 責務: [ImageMetrics: carry normalized evidence from image quality evaluators]
# フィールド: [fidelity, controllability, quality, base_preservation, leakage, memorization, diversity]
# 処理: [validate every metric in the shared 0..1 range]
# 引数: [metric values: evaluator measurements for one generated sample]
# 戻り値: [None: validated immutable metrics]
# }
@dataclass(frozen=True)
class ImageMetrics:
    fidelity: float
    controllability: float
    quality: float
    base_preservation: float
    leakage: float
    memorization: float
    diversity: float

    # {
    # 責務: [ImageMetrics.__post_init__: validate the declared immutable contract]
    # 処理: [1: reject nonfinite or out-of-range quality measurements]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        values = vars(self)
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
            raise ValueError("image quality metrics must be normalized to 0..1")


# {
# 責務: [EvaluationContext: pin one image evaluator call to repeatable conditions]
# フィールド: [scenario, seed, sampler, inference_steps, resolution, strength]
# 処理: [hold every inference variable except checkpoint and explicit sweep dimensions fixed]
# 引数: [context values: one deterministic sample request]
# 戻り値: [None: immutable evaluator context]
# }
@dataclass(frozen=True)
class EvaluationContext:
    scenario: PromptScenario
    seed: int
    sampler: str
    inference_steps: int
    resolution: tuple[int, int]
    strength: float

    # {
    # 責務: [EvaluationContext.__post_init__: validate one fixed rendering request]
    # 処理: [1: reject invalid seeds, sampler settings, resolution or inference strength]
    # 引数: [self: deterministic generation context]
    # 戻り値: [None: validated evaluation request]
    # }
    def __post_init__(self) -> None:
        width, height = self.resolution
        if (
            self.seed < 0
            or not self.sampler.strip()
            or self.inference_steps < 1
            or not 64 <= width <= 4096
            or not 64 <= height <= 4096
            or not math.isfinite(self.strength)
            or not 0 <= self.strength <= 2
        ):
            raise ValueError("invalid deterministic generation context")


# {
# 責務: [ImageEvidence: bind measured metrics to the rendered preview artifact]
# フィールド: [metrics, preview_path, sha256]
# 処理: [retain optional preview location and renderer-provided content identity]
# 引数: [metrics: quality evidence, preview_path: generated image, sha256: optional image digest]
# 戻り値: [None: immutable image evidence]
# }
@dataclass(frozen=True)
class ImageEvidence:
    metrics: ImageMetrics
    preview_path: Path | None = None
    sha256: str | None = None


# {
# 責務: [ValidationSample: preserve a generated validation result and its measurements]
# フィールド: [checkpoint, context, metrics]
# 処理: [retain the exact checkpoint and deterministic sample context]
# 引数: [checkpoint: evaluated model artifact, context: render settings, metrics: image evaluator evidence]
# 戻り値: [None: immutable sample evidence]
# }
@dataclass(frozen=True)
class ValidationSample:
    checkpoint: CheckpointRef
    context: EvaluationContext
    metrics: ImageMetrics
    preview_path: Path | None = None
    sha256: str | None = None


# {
# 責務: [CheckpointRef: identify one immutable trainer checkpoint]
# フィールド: [path, step]
# 処理: [normalize the local path and require a nonnegative step]
# 引数: [path: checkpoint artifact path, step: trainer step represented by the artifact]
# 戻り値: [None: validated checkpoint identity]
# }
@dataclass(frozen=True)
class CheckpointRef:
    path: Path
    step: int

    # {
    # 責務: [CheckpointRef.__post_init__: validate the declared immutable contract]
    # 処理: [1: reject negative checkpoint steps]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        if self.step < 0:
            raise ValueError("checkpoint step must not be negative")


# {
# 責務: [TrainingTracePoint: retain trainer diagnostics at one training step]
# フィールド: [step, loss, learning_rate, gradient_norm, timestep_distribution, vram_gib, step_seconds, checkpoint_size_bytes]
# 処理: [validate finite measurements and normalized timestep proportions]
# 引数: [diagnostic values: one trainer progress snapshot]
# 戻り値: [None: validated immutable trace point]
# }
@dataclass(frozen=True)
class TrainingTracePoint:
    step: int
    loss: float | None = None
    learning_rate: float | None = None
    gradient_norm: float | None = None
    timestep_distribution: tuple[float, ...] = ()
    vram_gib: float | None = None
    step_seconds: float | None = None
    checkpoint_size_bytes: int | None = None

    # {
    # 責務: [TrainingTracePoint.__post_init__: validate the declared immutable contract]
    # 処理: [1: validate finite trainer diagnostics and timestep proportions]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        optional = (
            self.loss,
            self.learning_rate,
            self.gradient_norm,
            self.vram_gib,
            self.step_seconds,
        )
        if self.step < 0 or any(
            value is not None and (not math.isfinite(value) or value < 0) for value in optional
        ):
            raise ValueError("training trace values must be nonnegative")
        if self.checkpoint_size_bytes is not None and self.checkpoint_size_bytes < 0:
            raise ValueError("checkpoint size must be nonnegative")
        if any(value < 0 or value > 1 for value in self.timestep_distribution):
            raise ValueError("timestep distribution values must be in 0..1")
        if self.timestep_distribution and abs(sum(self.timestep_distribution) - 1) > 0.02:
            raise ValueError("timestep distribution must sum to approximately one")


# {
# 責務: [ScoreWeights: configure task-specific balanced checkpoint objectives]
# フィールド: [weights for positive quality axes and overfit penalties]
# 処理: [require finite nonnegative weights with a positive total]
# 引数: [weight values: relative metric importance]
# 戻り値: [None: validated scoring profile]
# }
@dataclass(frozen=True)
class ScoreWeights:
    fidelity: float = 1.0
    controllability: float = 1.0
    quality: float = 1.0
    diversity: float = 0.8
    base_preservation: float = 0.8
    leakage: float = 1.2
    memorization: float = 1.0

    # {
    # 責務: [ScoreWeights.__post_init__: validate the declared immutable contract]
    # 処理: [1: require finite nonnegative weights with a positive total]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        values = vars(self)
        if (
            any(not math.isfinite(value) or value < 0 for value in values.values())
            or sum(values.values()) <= 0
        ):
            raise ValueError("score weights must be nonnegative with a positive total")


# {
# 責務: [EarlyStopPolicy: define patience and overfit guard thresholds]
# フィールド: [patience, minimum_improvement, signal_threshold, overfit_patience]
# 処理: [validate stopping thresholds]
# 引数: [policy values: consecutive non-improving checkpoints and metric tolerances]
# 戻り値: [None: validated early-stop policy]
# }
@dataclass(frozen=True)
class EarlyStopPolicy:
    patience: int = 3
    minimum_improvement: float = 0.01
    signal_threshold: float = 0.08
    overfit_patience: int = 2

    # {
    # 責務: [EarlyStopPolicy.__post_init__: validate the declared immutable contract]
    # 処理: [1: validate consecutive-stop patience and metric thresholds]
    # 引数: [self: contract instance]
    # 戻り値: [None: validated object or ValueError]
    # }

    def __post_init__(self) -> None:
        if self.patience < 1 or self.overfit_patience < 1:
            raise ValueError("early-stop patience must be positive")
        if not 0 <= self.minimum_improvement <= 1 or not 0 < self.signal_threshold <= 1:
            raise ValueError("early-stop thresholds must be in range")


# {
# 責務: [CheckpointAssessment: report score, overfit signals and selected inference strength]
# フィールド: [checkpoint, score, score_breakdown, recommended_strength, signals, samples]
# 処理: [retain per-checkpoint evidence and explain quality tradeoffs]
# 引数: [assessment values: checkpoint evaluator output]
# 戻り値: [None: immutable assessment]
# }
@dataclass(frozen=True)
class CheckpointAssessment:
    checkpoint: CheckpointRef
    score: float
    score_breakdown: dict[str, float]
    recommended_strength: float
    recommended_trigger: str
    signals: tuple[str, ...]
    samples: tuple[ValidationSample, ...]


# {
# 責務: [TrainingDoctorReport: present best checkpoint and reproducible training diagnostics]
# フィールド: [best_checkpoint, final_checkpoint, recommended_strength, recommended_trigger, score_breakdown, overfit_onset, leakage_score, base_preservation, validation_samples, training_curves, stop_reason, assessments]
# 処理: [serialize decision evidence without claiming unavailable measurements]
# 引数: [report values: completed training doctor analysis]
# 戻り値: [None: immutable report]
# }
@dataclass(frozen=True)
class TrainingDoctorReport:
    best_checkpoint: Path
    final_checkpoint: Path
    recommended_strength: float
    recommended_trigger: str
    score_breakdown: dict[str, float]
    overfit_onset: int | None
    leakage_score: float
    base_preservation: float
    validation_samples: tuple[ValidationSample, ...]
    training_curves: tuple[TrainingTracePoint, ...]
    stop_reason: str
    assessments: tuple[CheckpointAssessment, ...]
    recommended_tags: tuple[str, ...] = ()
    task: ValidationTask = ValidationTask.CHARACTER
    score_preset: ScorePreset = ScorePreset.BALANCED

    # {
    # 責務: [prompt_metadata: create additive LoRA recommendation metadata for prompt consumers]
    # 処理: [export recommended trigger, strength, checkpoint and score breakdown]
    # 引数: [self: completed training doctor report]
    # 戻り値: [dict[str, object]: portable prompt metadata fields]
    # }
    def prompt_metadata(self) -> dict[str, object]:
        """Create the additive LoRA recommendation metadata payload for prompt consumers."""
        return {
            "validation_task": self.task.value,
            "recommended_trigger": self.recommended_trigger,
            "recommended_prompt": ", ".join((self.recommended_trigger, *self.recommended_tags)),
            "recommended_tags": list(self.recommended_tags),
            "recommended_lora_strength": self.recommended_strength,
            "best_checkpoint": str(self.best_checkpoint),
            "training_doctor_score": self.score_breakdown,
            "score_preset": self.score_preset.value,
        }
