from dataclasses import dataclass

from .character_tag_candidate import CharacterTagCandidate


# {
#   責務: [CharacterOutfitTagGroup: outfit単位に集約したtag提案を保持する]
#   フィールド: [outfit_id: outfit profile IDまたはunassigned, is_unassigned: 実profile未割当groupか, tags: outfit tag候補]
# }
@dataclass(frozen=True)
class CharacterOutfitTagGroup:
    outfit_id: str
    is_unassigned: bool
    tags: tuple[CharacterTagCandidate, ...]
