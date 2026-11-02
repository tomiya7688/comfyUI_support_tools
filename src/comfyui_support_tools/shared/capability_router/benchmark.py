"""Fixed, versioned prompt cases for capability benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import GenerationUseCase


# {
#   責務: [CapabilityBenchmarkCase: task-specific repeated comparison inputを定義する]
#   フィールド: [case_id, use_case, prompt, selection_metric, resolution]
# }
@dataclass(frozen=True, slots=True)
class CapabilityBenchmarkCase:
    case_id: str
    use_case: GenerationUseCase
    prompt: str
    selection_metric: str
    resolution: tuple[int, int]

    # {
    #   責務: [__post_init__: benchmark caseのidentity, prompt and resolutionをvalidateする]
    #   処理: [reject empty test cases and dimensions below the supported minimum]
    #   引数: [self: fixed benchmark input]
    #   戻り値: []
    #   エラー: [ValueError: malformed benchmark case]
    # }
    def __post_init__(self) -> None:
        if not all((self.case_id.strip(), self.prompt.strip(), self.selection_metric.strip())):
            raise ValueError("benchmark cases require an ID, prompt and task metric")
        if not isinstance(self.use_case, GenerationUseCase):
            raise TypeError("benchmark case use_case must be declared")
        if any(isinstance(value, bool) or value < 64 for value in self.resolution):
            raise ValueError("benchmark resolution dimensions must be at least 64")


# {
#   責務: [create_default_benchmark_matrix: representative fixed promptsをtask category別に返す]
#   処理: [return versionable prompt inputs without claiming any model benchmark result]
#   引数: []
#   戻り値: [tuple[CapabilityBenchmarkCase, ...]: versionable evaluation matrix]
#   注意: [これらはbenchmark inputsで, 実際のmodel scoreを表さない]
# }
def create_default_benchmark_matrix() -> tuple[CapabilityBenchmarkCase, ...]:
    return (
        CapabilityBenchmarkCase(
            "photo_market_street_v1",
            GenerationUseCase.PHOTOREALISTIC,
            "A documentary photograph of a quiet morning market street after rain, natural light, readable signs, no people in foreground",
            "prompt_alignment",
            (1024, 768),
        ),
        CapabilityBenchmarkCase(
            "anime_character_portrait_v1",
            GenerationUseCase.ANIME,
            "one young adult woman, short blue hair, red scarf, standing pose, simple warm background, clean anime illustration",
            "tag_adherence",
            (768, 1024),
        ),
        CapabilityBenchmarkCase(
            "landscape_depth_v1",
            GenerationUseCase.LANDSCAPE,
            "wide coastal landscape, foreground grasses, middle-distance cliffs, distant lighthouse, overcast afternoon light",
            "composition_adherence",
            (1024, 768),
        ),
        CapabilityBenchmarkCase(
            "poster_typography_v1",
            GenerationUseCase.TYPOGRAPHY,
            "Minimal concert poster with the exact headline 'NIGHT MARKET', centered title, two-color geometric layout, clean margins",
            "ocr_exactness",
            (1024, 1024),
        ),
        CapabilityBenchmarkCase(
            "transparent_product_v1",
            GenerationUseCase.TRANSPARENT_ASSET,
            "single ceramic tea cup, three-quarter view, isolated transparent background, soft product lighting",
            "alpha_background_and_prompt_alignment",
            (768, 768),
        ),
    )
