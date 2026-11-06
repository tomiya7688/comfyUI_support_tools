from pathlib import Path

from .data.processing.character_wildcard_file_store import CharacterWildcardFileStore
from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    fetch_civitai_lora_version as _fetch_civitai_lora_version,
)
from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    preview_character_intake as _preview_character_intake,
)
from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    register_character_intake as _register_character_intake,
)
from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    search_civitai_loras as _search_civitai_loras,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_wildcard_exporter import (
    build_character_wildcard_files as _build_character_wildcard_files,
)
from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id
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
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)


# {
#   責務: [search_civitai_loras: public APIからLoRA候補と利用条件を検索する]
#   処理: [query/limit/cursorをclientへ渡し, version別candidateと次cursorを返す]
#   引数: [query: 検索語, limit: 1〜100のページサイズ, cursor: 次ページ位置]
#   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: 候補とcursor]
#   エラー: [ValueError: 入力不正, RuntimeError: Civitai API失敗またはresponse不正]
# }
def search_civitai_loras(
    query: str,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
    """Search public Civitai LoRA metadata without downloading model files."""
    return _search_civitai_loras(query, limit=limit, cursor=cursor)


# {
#   責務: [fetch_civitai_lora_version: 選択済みLoRA versionのtrigger metadataを取得する]
#   処理: [data clientへcandidateを渡し, trainedWordsとversion状態を返す]
#   引数: [candidate: search結果から選んだversion候補]
#   戻り値: [CivitaiLoraVersionMetadata: trigger wordsとpublication状態]
#   エラー: [ValueError: candidate不正, RuntimeError: Civitai API失敗またはID不一致]
# }
def fetch_civitai_lora_version(
    candidate: CivitaiLoraCandidate,
) -> CivitaiLoraVersionMetadata:
    """Fetch trigger metadata for a selected version; never fetch its weights."""
    return _fetch_civitai_lora_version(candidate)


# {
#   責務: [preview_character_intake: API入力を検証して登録候補previewを返す]
#   処理: [character ID/display name/root/Civitai candidateを検証し, process commanderへ委譲する]
#   引数: [request: Character Registry intake request, civitai_candidate: 任意のLoRA version候補]
#   戻り値: [CharacterTagIntakePreview: identity/outfit/context/unclassified候補とsource provenance]
#   エラー: [ValueError: ID, name, root, candidateが不正な場合, RuntimeError: 選択版metadataの取得に失敗した場合]
# }
def preview_character_intake(
    request: CharacterTagIntakeRequest,
    civitai_candidate: CivitaiLoraCandidate | None = None,
) -> CharacterTagIntakePreview:
    """Return identity/outfit/unclassified tag suggestions for manual review."""
    if not is_valid_character_id(request.character_id):
        raise ValueError("character_idは小文字英数字と-_を使う1〜64文字で指定してください")
    if not request.display_name.strip():
        raise ValueError("display_nameを指定してください")
    if not isinstance(request.dataset_root, Path):
        raise ValueError("dataset_root must be a pathlib.Path")
    if civitai_candidate is not None and not isinstance(civitai_candidate, CivitaiLoraCandidate):
        raise ValueError("civitai_candidateはCivitaiLoraCandidateで指定してください")
    return _preview_character_intake(request, civitai_candidate)


# {
#   責務: [register_character_intake: 人が確認したintake結果を新規CharacterProfileとして登録する]
#   処理: [preview/confirmation/storage rootを検証し, commanderへ保存を依頼する]
#   引数: [preview: tag intake preview, confirmation: 明示的な手動確認内容, profile_directory: 設定済み保存root]
#   戻り値: [CharacterProfile: 登録profile]
#   エラー: [ValueError: 入力が不正, FileExistsError: character_id登録済み, OSError: 保存失敗]
# }
def register_character_intake(
    preview: CharacterTagIntakePreview,
    confirmation: CharacterTagIntakeConfirmation,
    profile_directory: Path,
) -> CharacterProfile:
    if not isinstance(preview, CharacterTagIntakePreview):
        raise ValueError("previewはCharacterTagIntakePreviewで指定してください")
    if not isinstance(confirmation, CharacterTagIntakeConfirmation):
        raise ValueError("confirmationはCharacterTagIntakeConfirmationで指定してください")
    if not isinstance(profile_directory, Path):
        raise ValueError("profile_directoryはpathlib.Pathで指定してください")
    return _register_character_intake(preview, confirmation, profile_directory)


# {
#   責務: [build_character_wildcard_files: public APIから確認済みCharacterProfileのwildcard bundleを作る]
#   処理: [process exporterへprofileの変換を委譲する]
#   引数: [profile: 書き出すCharacterProfile]
#   戻り値: [dict[str, str]: root相対wildcard pathと本文の対応]
#   エラー: [ValueError: 確認済みidentityがない等, profileを安全に書き出せない場合]
# }
def build_character_wildcard_files(profile: CharacterProfile) -> dict[str, str]:
    """Build a filesystem-independent wildcard bundle from a confirmed profile."""
    if not isinstance(profile, CharacterProfile):
        raise ValueError("profileはCharacterProfileで指定してください")
    return _build_character_wildcard_files(profile)


# {
#   責務: [write_character_wildcard_files: 確認済みprofileをwildcard rootへ保存する]
#   処理: [public exporterでbundleを作り, UIから渡されたrootへfile store経由で書く]
#   引数: [profile: 書き出すCharacterProfile, wildcard_root: paths.json由来のwildcard保存root]
#   戻り値: [tuple[Path, ...]: 書き出したabsolute file path]
#   エラー: [ValueError: profileまたはrootが不正, OSError: filesystem保存に失敗]
# }
def write_character_wildcard_files(
    profile: CharacterProfile,
    wildcard_root: Path,
) -> tuple[Path, ...]:
    if not isinstance(profile, CharacterProfile):
        raise ValueError("profileはCharacterProfileで指定してください")
    if not isinstance(wildcard_root, Path):
        raise ValueError("wildcard_rootはpathlib.Pathで指定してください")
    files = _build_character_wildcard_files(profile)
    return CharacterWildcardFileStore().write(wildcard_root, files)
