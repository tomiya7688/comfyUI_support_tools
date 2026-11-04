from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    preview_character_intake as _preview_character_intake,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id


# {
#   責務: [preview_character_intake: API入力を検証して登録候補previewを返す]
#   処理: [character ID/display name/rootを検証し, process messengerへ委譲する]
#   引数: [request: Character Registry intake request]
#   戻り値: [CharacterTagIntakePreview: identity/outfit/context/unclassified候補とsource provenance]
#   エラー: [ValueError: ID, name, rootが不正な場合]
# }
def preview_character_intake(request: CharacterTagIntakeRequest) -> CharacterTagIntakePreview:
    """Return identity/outfit/unclassified tag suggestions for manual review."""
    if not is_valid_character_id(request.character_id):
        raise ValueError("character_idは小文字英数字と-_を使う1〜64文字で指定してください")
    if not request.display_name.strip():
        raise ValueError("display_nameを指定してください")
    if not isinstance(request.dataset_root, Path):
        raise ValueError("dataset_root must be a pathlib.Path")
    return _preview_character_intake(request)
