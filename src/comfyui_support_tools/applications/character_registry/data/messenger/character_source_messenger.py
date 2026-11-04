from pathlib import Path

from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset

from ..processing.tagged_dataset_reader import read_tagged_dataset


# {
#   責務: [load_character_sources: Character Registry processへtagged assetを渡す]
#   処理: [dataset readerにcaption読込とmanifest検証を依頼する]
#   引数: [dataset_root: source dataset directory]
#   戻り値: [tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]: asset一覧とwarning]
# }
def load_character_sources(
    dataset_root: Path,
) -> tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]:
    """Load tagged image assets without discarding provenance warnings."""
    return read_tagged_dataset(dataset_root)
