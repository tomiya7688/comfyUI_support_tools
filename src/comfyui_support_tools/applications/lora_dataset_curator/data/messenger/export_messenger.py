"""In-process messenger for trainer dataset export requests."""

from pathlib import Path

from comfyui_support_tools.applications.lora_dataset_curator.data.processing.export import (
    export_dataset,
)
from comfyui_support_tools.shared.contracts.dataset_curator import DatasetAnalysis


# {
# 責務: [DatasetExportMessenger: route an export request to Data processing]
# フィールド: [no mutable state]
# 処理: [preserve an explicit Process-to-Data boundary for export requests]
# }
class DatasetExportMessenger:
    # {
    # 責務: [export: send a reviewed analysis to Data export processing]
    # 処理: [pass the curation value object and requested destination/trainer to the Data implementation]
    # 引数: [self: messenger, analysis: reviewed dataset, destination: new output directory, trainer: output format]
    # 戻り値: [Path: exported dataset path]
    # }
    def export(self, analysis: DatasetAnalysis, destination: str | Path, trainer: str) -> Path:
        return export_dataset(analysis, destination, trainer)
