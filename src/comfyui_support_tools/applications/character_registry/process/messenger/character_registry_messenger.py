from src.comfyui_support_tools.applications.character_registry.data.messenger.character_source_messenger import (
    load_character_sources,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_tag_intake_processor import (
    build_character_tag_preview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)


# {
#   責務: [preview_character_intake: source読み込みと分類処理を束ねる]
#   処理: [1: data messengerからtagged assetsを取得する, 2: processへ分類を依頼する]
#   引数: [request: Character Registry intake request]
#   戻り値: [CharacterTagIntakePreview: 登録前の分類preview]
# }
def preview_character_intake(request: CharacterTagIntakeRequest) -> CharacterTagIntakePreview:
    """Build a reviewable tag preview without mutating the Character Registry."""
    assets, warnings = load_character_sources(request.dataset_root)
    return build_character_tag_preview(request, assets, warnings)
