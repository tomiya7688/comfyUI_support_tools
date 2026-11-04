from dataclasses import dataclass


# {
#   責務: [CharacterTagCandidate: 分類されたtag提案と出現情報を保持する]
#   フィールド: [tag: 原tag, category: identity/outfit/unclassified, count: 出現asset数, confidence: 分類確度, source_files: 出現caption一覧]
# }
@dataclass(frozen=True)
class CharacterTagCandidate:
    tag: str
    category: str
    count: int
    confidence: float
    source_files: tuple[str, ...]
