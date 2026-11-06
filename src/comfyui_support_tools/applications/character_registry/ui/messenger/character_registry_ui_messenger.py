from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.api import (
    preview_character_intake,
    register_character_intake,
    search_civitai_loras,
    write_character_lora_call_wildcard,
    write_character_wildcard_files,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)


# {
#   責務: [CharacterRegistryUiMessenger: Character Registry UIからpublic application APIへrequestを渡す]
#   フィールド: [なし]
# }
class CharacterRegistryUiMessenger:
    """Expose only public Character Registry API calls to the UI layer."""

    # {
    #   責務: [search_civitai_loras: UIの検索語でCivitai LoRA候補を取得する]
    #   処理: [public APIを呼び, 候補とpagination cursorを返す]
    #   引数: [query: Civitai検索語]
    #   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: 候補一覧と次cursor]
    # }
    def search_civitai_loras(
        self, query: str, cursor: str | None = None
    ) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
        """Search one metadata-only Civitai page using the optional next cursor."""
        return search_civitai_loras(query, limit=30, cursor=cursor)

    # {
    #   責務: [preview_character_intake: UIのsourceと選択LoRAから分類previewを取得する]
    #   処理: [public APIへrequestと任意のCivitai candidateを渡す]
    #   引数: [request: intake条件, candidate: 選択LoRA version]
    #   戻り値: [CharacterTagIntakePreview: 手動確認する分類候補]
    # }
    def preview_character_intake(
        self,
        request: CharacterTagIntakeRequest,
        candidate: CivitaiLoraCandidate | None,
    ) -> CharacterTagIntakePreview:
        return preview_character_intake(request, candidate)

    # {
    #   責務: [register_character_intake: 手動確認内容をCharacterProfileとして登録する]
    #   処理: [public APIへpreview, confirmation, profile rootを渡す]
    #   引数: [preview: intake preview, confirmation: 手動確認内容, profile_directory: 設定済み保存root]
    #   戻り値: [CharacterProfile: 登録したprofile]
    # }
    def register_character_intake(
        self,
        preview: CharacterTagIntakePreview,
        confirmation: CharacterTagIntakeConfirmation,
        profile_directory: Path,
    ) -> CharacterProfile:
        return register_character_intake(preview, confirmation, profile_directory)

    # {
    #   責務: [write_character_wildcard_files: 登録済みprofileのwildcardを設定rootへ出力する]
    #   処理: [public APIへprofileとwildcard rootを渡し, 保存path一覧を返す]
    #   引数: [profile: 保存済みCharacterProfile, wildcard_root: configured wildcard root]
    #   戻り値: [tuple[Path, ...]: 書き出したfile path]
    # }
    def write_character_wildcard_files(
        self,
        profile: CharacterProfile,
        wildcard_root: Path,
    ) -> tuple[Path, ...]:
        return write_character_wildcard_files(profile, wildcard_root)

    # {
    #   責務: [write_character_lora_call_wildcard: UIのLoRA候補をpublic API経由で保存する]
    #   処理: [Character ID,候補本文,wildcard rootをAPIへ渡す]
    #   引数: [character_id: stable ID, content: LoRA候補本文, wildcard_root: 設定済みroot]
    #   戻り値: [tuple[Path, ...]: 保存path]
    # }
    def write_character_lora_call_wildcard(
        self,
        character_id: str,
        content: str,
        wildcard_root: Path,
    ) -> tuple[Path, ...]:
        """Persist weighted LoRA-call lines for a registered Character."""
        return write_character_lora_call_wildcard(character_id, content, wildcard_root)
