from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.process.commander.character_registry_commander import (
    fetch_civitai_lora_version as _fetch_civitai_lora_version,
    preview_character_intake as _preview_character_intake,
    search_civitai_loras as _search_civitai_loras,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_wildcard_exporter import (
    build_character_wildcard_files as _build_character_wildcard_files,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id
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
