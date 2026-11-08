from dataclasses import dataclass
from pathlib import Path
import re


# {
#   責務: [CharacterReferenceImage: コピーしない参照画像と内容ハッシュを保持する]
#   フィールド: [image_id: sha256由来のstable ID, source_path: 元画像の絶対path, content_sha256: 画像内容のdigest]
# }
@dataclass(frozen=True)
class CharacterReferenceImage:
    image_id: str
    source_path: str
    content_sha256: str

    # {
    #   責務: [__post_init__: 参照画像のID/path/hash形式を検証する]
    #   処理: [SHA-256形式, IDとの一致, 絶対pathを検証する]
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
