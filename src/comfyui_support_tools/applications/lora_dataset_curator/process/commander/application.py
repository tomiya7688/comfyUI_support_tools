"""Application orchestration for LoRA dataset analysis and trainer export."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from comfyui_support_tools.applications.lora_dataset_curator.process.messenger.dataset_export_messenger import (
    DatasetExportMessenger,
)
from comfyui_support_tools.applications.lora_dataset_curator.process.processing.curation import (
    DatasetCurationProcessor,
)
from comfyui_support_tools.shared.contracts.dataset_curator import (
    CaptionPolicyProbe,
    CuratorConfig,
    DatasetAnalysis,
    DatasetSampleInput,
    EmbeddingSimilarityProvider,
    ImageEvidenceProvider,
    SampleOverride,
)


# {
# 責務: [DatasetCuratorApplication: orchestrate curation, probe comparison and trainer export]
# フィールド: [curation processor]
# 処理: [route requests across Process and Data layer operations]
# 引数: [processor: injectable curation implementation]
# 戻り値: [DatasetCuratorApplication: application boundary]
# }
class DatasetCuratorApplication:
    # {
    # 責務: [__init__: bind an application-level processor]
    # 処理: [store the deterministic curation service]
    # 引数: [self: application instance, processor: optional curation processor]
    # 戻り値: [None: application initialized]
    # }
    def __init__(
        self,
        processor: DatasetCurationProcessor | None = None,
        export_messenger: DatasetExportMessenger | None = None,
    ) -> None:
        self._processor = processor or DatasetCurationProcessor()
        self._export_messenger = export_messenger or DatasetExportMessenger()

    # {
    # 責務: [curate: produce task-aware dataset plan]
    # 処理: [delegate curation to Process processing]
    # 引数: [root: dataset directory, config: curation controls, samples: optional explicit inventory, overrides: manual decisions, regularization_images: separate prior images, evidence_provider: optional local vision adapter, similarity_provider: optional local similarity adapter]
    # 戻り値: [DatasetAnalysis: auditable dataset plan]
    # }
    def curate(
        self,
        root: str | Path,
        config: CuratorConfig,
        samples: Sequence[DatasetSampleInput] | None = None,
        overrides: Sequence[SampleOverride] = (),
        regularization_images: Sequence[str | Path] = (),
        evidence_provider: ImageEvidenceProvider | None = None,
        similarity_provider: EmbeddingSimilarityProvider | None = None,
    ) -> DatasetAnalysis:
        return self._processor.curate(
            root,
            config,
            samples,
            overrides,
            regularization_images,
            evidence_provider,
            similarity_provider,
        )

    # {
    # 責務: [compare_caption_policies: request optional #55 caption-policy probe]
    # 処理: [delegate candidate evaluation to Process processing]
    # 引数: [analysis: curation result, probe: local trainer probe adapter]
    # 戻り値: [tuple[tuple[str, float], ...]: best-first normalized scores]
    # }
    def compare_caption_policies(
        self, analysis: DatasetAnalysis, probe: CaptionPolicyProbe
    ) -> tuple[tuple[str, float], ...]:
        return self._processor.compare_caption_policies(analysis, probe)

    # {
    # 責務: [export: write the final dataset through the Data layer]
    # 処理: [delegate a transactional trainer-compatible copy]
    # 引数: [analysis: reviewed curation result, destination: new local directory, trainer: supported target trainer]
    # 戻り値: [Path: published output directory]
    # }
    def export(self, analysis: DatasetAnalysis, destination: str | Path, trainer: str) -> Path:
        return self._export_messenger.export(analysis, destination, trainer)
