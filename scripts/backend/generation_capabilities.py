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


# {
#   責務: [GenerationCapabilities: generation backendが提供する機能一覧を保持する]
#   フィールド: [features: 対応するGenerationFeatureのimmutable set]
#   処理: [backend adapterと利用側で共通の機能契約を共有する]
# }
@dataclass(frozen=True)
class GenerationCapabilities:
    features: frozenset[GenerationFeature]

    # {
    #   責務: [supports: 指定されたgeneration機能に対応するか判定する]
    #   処理: [featuresに指定機能が含まれるか確認して結果を返す]
    #   引数: [self: capability宣言, feature: 確認するGenerationFeature]
    #   戻り値: [bool: 機能が提供される場合true]
    # }
    def supports(self, feature: GenerationFeature) -> bool:
        return feature in self.features

    # {
    #   責務: [require: 呼び出しに必要なgeneration機能があることを検証する]
    #   処理: [未対応機能の場合は共通のValueErrorを送出する]
    #   引数: [self: capability宣言, feature: 必須のGenerationFeature]
    #   戻り値: []
    #   エラー: [ValueError: backendが必須機能に対応していない場合]
    # }
    def require(self, feature: GenerationFeature) -> None:
        if not self.supports(feature):
            raise ValueError(f"Generation backend does not support required capability: {feature}")
