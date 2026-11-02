"""Transport dataset export requests across the Process/Data boundary."""

from pathlib import Path

from comfyui_support_tools.applications.lora_dataset_curator.data.messenger.export_messenger import (
    DatasetExportMessenger as DataExportTarget,
)
from comfyui_support_tools.shared.contracts.dataset_curator import DatasetAnalysis


# {
# 責務: [DatasetExportMessenger: route a Process export request to Data]
# フィールド: [Data messenger target]
# 処理: [transport export payload without interpreting curation decisions]
# }
class DatasetExportMessenger:
    # {
    # 責務: [__init__: bind the Data-side messenger endpoint]
    # 処理: [store an injectable in-process target]
    # 引数: [self: messenger, target: Data export messenger]
    # 戻り値: [None: endpoint bound]
    # }
    def __init__(self, target: DataExportTarget | None = None) -> None:
        self._target = target or DataExportTarget()

    # {
    # 責務: [export: transport a reviewed dataset export request]
    # 処理: [forward the curation value object, destination, and trainer]
    # 引数: [self: messenger, analysis: reviewed dataset, destination: new output directory, trainer: output format]
    # 戻り値: [Path: exported dataset path]
    # }
    def export(self, analysis: DatasetAnalysis, destination: str | Path, trainer: str) -> Path:
        return self._target.export(analysis, destination, trainer)
