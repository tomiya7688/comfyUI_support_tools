from dataclasses import dataclass

from .character_outfit_tag_group import CharacterOutfitTagGroup
from .character_source_asset import CharacterSourceAsset
from .character_tag_candidate import CharacterTagCandidate


# {
#   責務: [CharacterTagIntakePreview: 登録前に確認するタグ分類とsource provenanceを保持する]
#   フィールド: [character_id: stable identifier, display_name: 表示名, aliases: 別名, identity_candidates: identity候補, outfit_groups: outfit別tag候補, context_candidates: pose/expression/scene候補, unclassified_candidates: 未分類候補, source_assets: provenance付きsource, warnings: 要確認事項]
# }
@dataclass(frozen=True)
class CharacterTagIntakePreview:
    character_id: str
    display_name: str
    aliases: tuple[str, ...]
    identity_candidates: tuple[CharacterTagCandidate, ...]
    outfit_groups: tuple[CharacterOutfitTagGroup, ...]
    context_candidates: tuple[CharacterTagCandidate, ...]
    unclassified_candidates: tuple[CharacterTagCandidate, ...]
    source_assets: tuple[CharacterSourceAsset, ...]
    warnings: tuple[str, ...]
