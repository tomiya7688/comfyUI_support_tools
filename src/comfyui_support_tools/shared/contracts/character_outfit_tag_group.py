from dataclasses import dataclass

from .character_tag_candidate import CharacterTagCandidate


# {
#   責務: [CharacterOutfitTagGroup: outfit単位に集約したtag提案を保持する]
#   フィールド: [outfit_id: outfit profile IDまたはunassigned, tags: outfit tag候補]
# }
@dataclass(frozen=True)
class CharacterOutfitTagGroup:
    outfit_id: str
    tags: tuple[CharacterTagCandidate, ...]
