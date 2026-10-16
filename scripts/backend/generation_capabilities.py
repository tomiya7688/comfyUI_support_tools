"""Feature declarations shared by generation backends and callers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


# {
#   責務: [GenerationFeature: generation adapter capabilityで宣言可能な機能名を制約する]
#   許可値: [txt2img, img2img, interrupt, hires_fix, model_catalog, sampler_catalog, upscaler_catalog, vae_override, nudenet_mosaic, workflow, model_overrides]
# }
GenerationFeature: TypeAlias = Literal[
    "txt2img",
    "img2img",
    "interrupt",
    "hires_fix",
    "model_catalog",
    "sampler_catalog",
    "upscaler_catalog",
    "vae_override",
    "nudenet_mosaic",
    "workflow",
    "model_overrides",
]


@dataclass(frozen=True)
class GenerationCapabilities:
    features: frozenset[GenerationFeature]

    def supports(self, feature: GenerationFeature) -> bool:
        return feature in self.features
