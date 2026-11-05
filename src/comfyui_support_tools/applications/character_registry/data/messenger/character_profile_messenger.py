from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.data.processing.character_profile_store import (
    CharacterProfileStore,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile


# {
#   責務: [save_character_profile: CharacterProfileを指定directoryへ永続化する]
#   処理: [data storeを生成してatomic saveを委譲する]
#   引数: [profile: 保存するprofile, profile_directory: 設定から解決した保存先]
#   戻り値: [Path: 保存したprofile file]
#   エラー: [FileExistsError: 同じcharacter_idが既に存在する場合, OSError: 保存失敗, ValueError: profileまたは保存先が不正な場合]
# }
def save_character_profile(profile: CharacterProfile, profile_directory: Path) -> Path:
    store = CharacterProfileStore(profile_directory)
    try:
        store.load(profile.character_id)
    except FileNotFoundError:
        return store.save(profile)
    raise FileExistsError(f"character_idは既に登録されています: {profile.character_id}")
