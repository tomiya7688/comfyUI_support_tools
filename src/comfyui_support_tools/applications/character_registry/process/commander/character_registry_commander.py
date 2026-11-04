from src.comfyui_support_tools.applications.character_registry.process.messenger.character_source_requests import (
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
#   責務: [preview_character_intake: source取得とtag分類の処理順を調整する]
#   処理: [1: data messengerからsourceを取得する, 2: process processingへpreview構築を依頼する]
#   引数: [request: Character Registry intake request]
#   戻り値: [CharacterTagIntakePreview: provenance付き分類候補]
# }
def preview_character_intake(request: CharacterTagIntakeRequest) -> CharacterTagIntakePreview:
    assets, warnings = load_character_sources(request.dataset_root)
    return build_character_tag_preview(request, assets, warnings)
