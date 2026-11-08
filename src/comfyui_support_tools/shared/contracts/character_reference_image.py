import re
from dataclasses import dataclass
from pathlib import Path

from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id


# {
#   責務: [CharacterReferenceImage: コピーしない参照画像と内容ハッシュを保持する]
#   フィールド: [image_id: sha256由来のstable ID, source_path: 元画像の絶対path, content_sha256: 画像内容のdigest, outfit_assignment: unknown/mixed_custom/outfit, outfit_id: outfit割当時のID, selected_for_training: 明示的に学習候補へ含めるか]
# }
@dataclass(frozen=True)
class CharacterReferenceImage:
    image_id: str
    source_path: str
    content_sha256: str
    outfit_assignment: str = "unknown"
    outfit_id: str | None = None
    selected_for_training: bool = False

    # {
    #   責務: [__post_init__: 参照画像のID/path/hash/outfit割当形式を検証する]
    #   処理: [SHA-256形式, ID一致, 絶対path, unknown/mixed/outfit割当, 学習候補boolを検証する]
    #   引数: [self: reference image]
    #   戻り値: []
    #   エラー: [ValueError: 参照画像metadataが不正な場合]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.content_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.content_sha256
        ):
            raise ValueError("content_sha256は小文字64桁のSHA-256で指定してください")
        if self.image_id != f"sha256-{self.content_sha256}":
            raise ValueError("image_idはcontent_sha256から生成してください")
        if not isinstance(self.source_path, str) or not self.source_path.strip():
            raise ValueError("source_pathを指定してください")
        if not Path(self.source_path).is_absolute():
            raise ValueError("source_pathは絶対pathで指定してください")
        if not isinstance(self.outfit_assignment, str) or self.outfit_assignment not in {
            "unknown",
            "mixed_custom",
            "outfit",
        }:
            raise ValueError("outfit_assignmentはunknown/mixed_custom/outfitで指定してください")
        if self.outfit_assignment == "outfit":
            if not isinstance(self.outfit_id, str) or not is_valid_character_id(self.outfit_id):
                raise ValueError("outfit割当では有効なoutfit_idを指定してください")
        elif self.outfit_id is not None:
            raise ValueError("unknown/mixed_customの画像にoutfit_idは指定できません")
        if not isinstance(self.selected_for_training, bool):
            raise ValueError("selected_for_trainingはboolで指定してください")
