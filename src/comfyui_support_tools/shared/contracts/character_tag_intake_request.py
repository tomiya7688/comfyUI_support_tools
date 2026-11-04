from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [CharacterTagIntakeRequest: tagged dataset previewの要求値を保持する]
#   フィールド: [character_id: stable identifier, display_name: 表示名, aliases: 別名, dataset_root: Tagger captionとmanifestのroot]
# }
@dataclass(frozen=True)
class CharacterTagIntakeRequest:
    character_id: str
    display_name: str
    aliases: tuple[str, ...]
    dataset_root: Path
