import hashlib
from pathlib import Path

from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)

SUPPORTED_REFERENCE_IMAGE_SUFFIXES = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
HASH_CHUNK_SIZE = 1024 * 1024


# {
#   責務: [load_character_reference_image: 画像ファイルのstable IDと参照pathを作る]
#   処理: [画像形式とfileを検証し, chunk単位でSHA-256を計算する]
#   引数: [image_path: 利用者が選択した画像path]
#   戻り値: [CharacterReferenceImage: コピーを作らない画像参照]
#   エラー: [ValueError: unsupported imageまたは読み込めないfile]
# }
def load_character_reference_image(image_path: str | Path) -> CharacterReferenceImage:
    path = Path(image_path).expanduser()
    if path.suffix.lower() not in SUPPORTED_REFERENCE_IMAGE_SUFFIXES:
        raise ValueError(f"未対応の画像形式です: {path.name}")
    try:
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_file():
            raise ValueError(f"画像fileではありません: {path}")
        digest = _sha256_file(resolved_path)
    except OSError as error:
        raise ValueError(f"画像を読み込めません: {path}: {error}") from error
    return CharacterReferenceImage(
        image_id=f"sha256-{digest}",
        source_path=str(resolved_path),
        content_sha256=digest,
    )


# {
#   責務: [_sha256_file: file内容をSHA-256へ変換する]
#   処理: [大きな画像を固定size chunkで順にhashへ渡す]
#   引数: [path: 読み込むfile]
#   戻り値: [str: 小文字64桁のSHA-256]
# }
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
