from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.data.messenger.character_source_messenger import (
    load_character_sources as _load_character_sources,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset


# {
#   責務: [load_character_sources: Data layerへdataset読込を配送する]
#   処理: [requestをdata messengerへ渡し, source assetsとwarningを返す]
#   引数: [dataset_root: 明示されたdataset root]
#   戻り値: [tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]: provenance付きsourceとwarning]
# }
def load_character_sources(
    dataset_root: Path,
) -> tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]:
    return _load_character_sources(dataset_root)
