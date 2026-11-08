from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.data.messenger.character_profile_messenger import (
    save_character_profile as _save_character_profile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile


# {
#   責務: [save_character_profile: Data layerへprofile保存を配送する]
#   処理: [profileと明示された保存directoryをdata messengerへ渡す]
#   引数: [profile: 永続化するCharacterProfile, profile_directory: 設定済みprofile root]
#   戻り値: [Path: 保存先file]
#   エラー: [FileExistsError: 同じcharacter_idが登録済み, OSError: 保存失敗, ValueError: profile不正]
# }
def save_character_profile(profile: CharacterProfile, profile_directory: Path) -> Path:
    return _save_character_profile(profile, profile_directory)
