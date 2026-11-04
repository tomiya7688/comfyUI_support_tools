from collections import defaultdict

from src.comfyui_support_tools.shared.contracts.character_outfit_tag_group import (
    CharacterOutfitTagGroup,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.character_tag_candidate import CharacterTagCandidate
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)

from .character_tag_taxonomy import classify_character_tag


# {
#   責務: [_candidate_list: asset横断でtag出現数とsource fileを集約する]
#   処理: [tagごとにcaptionを重複なしで数え, confidenceとsource一覧付き候補へ変換する]
#   引数: [tag_sources: tagからcaption file集合へのmapping, category: candidate category, confidence: 分類confidence]
#   戻り値: [tuple[CharacterTagCandidate, ...]: 出現数順のtag候補]
# }
def _candidate_list(
    tag_sources: dict[str, set[str]],
    category: str,
    confidence: float,
) -> tuple[CharacterTagCandidate, ...]:
    return tuple(
        CharacterTagCandidate(tag, category, len(files), confidence, tuple(sorted(files)))
        for tag, files in sorted(
            tag_sources.items(), key=lambda item: (-len(item[1]), item[0].casefold())
        )
    )


# {
#   責務: [build_character_tag_preview: tagger caption群から登録前の分類previewを作る]
#   処理: [1: tag taxonomyで候補分類する, 2: outfit directory別に集約する, 3: provenance warningをpreviewへ残す]
#   引数: [request: intake request, assets: source asset一覧, source_warnings: reader警告]
#   戻り値: [CharacterTagIntakePreview: 手動確認可能な分類結果]
# }
def build_character_tag_preview(
    request: CharacterTagIntakeRequest,
    assets: tuple[CharacterSourceAsset, ...],
    source_warnings: tuple[str, ...],
) -> CharacterTagIntakePreview:
    identity_sources: dict[str, set[str]] = defaultdict(set)
    context_sources: dict[str, set[str]] = defaultdict(set)
    unclassified_sources: dict[str, set[str]] = defaultdict(set)
    outfit_sources: dict[tuple[str, bool], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for asset in assets:
        for tag in asset.tags:
            category = classify_character_tag(tag)
            if category == "identity":
                identity_sources[tag].add(asset.caption_file)
            elif category == "outfit":
                outfit_id = asset.outfit_id or "unassigned"
                outfit_sources[(outfit_id, asset.outfit_id is None)][tag].add(asset.caption_file)
            elif category == "context":
                context_sources[tag].add(asset.caption_file)
            else:
                unclassified_sources[tag].add(asset.caption_file)
    outfit_groups = tuple(
        CharacterOutfitTagGroup(outfit_id, is_unassigned, _candidate_list(tags, "outfit", 0.85))
        for (outfit_id, is_unassigned), tags in sorted(outfit_sources.items())
    )
    warnings = list(source_warnings)
    if unclassified_sources:
        warnings.append("未分類tagはidentity/outfitへ自動登録せず、手動確認してください。")
    if any(
        asset.license_status.casefold() == "unknown"
        or asset.training_permission.casefold() == "unknown"
        for asset in assets
    ):
        warnings.append(
            "利用条件がunknownのsourceがあります。学習利用前に権利情報を確認してください。"
        )
    return CharacterTagIntakePreview(
        character_id=request.character_id,
        display_name=request.display_name,
        aliases=request.aliases,
        identity_candidates=_candidate_list(identity_sources, "identity", 0.85),
        outfit_groups=outfit_groups,
        context_candidates=_candidate_list(context_sources, "context", 0.85),
        unclassified_candidates=_candidate_list(unclassified_sources, "unclassified", 0.0),
        source_assets=assets,
        warnings=tuple(dict.fromkeys(warnings)),
    )
