"""Register character images as source references and optional managed copies."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from enum import Enum
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from PIL import Image, UnidentifiedImageError

from comfyui_support_tools.shared.contracts.character_registry import CharacterImage

IMAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


# {
#   責務: [ImageStorageMode: registration時のsource/managed image保存方針を定義する]
#   フィールド: [reference、managed WebP、original + WebP]
# }
class ImageStorageMode(str, Enum):
    REFERENCE = "reference"
    MANAGED_WEBP = "managed_webp"
    ORIGINAL_AND_WEBP = "original_and_webp"


# {
#   責務: [register_character_image: source hash/geometryと選択保存形式でCharacterImageを作る]
#   処理: [1: source imageを検証する 2: exact duplicateを拒否する 3: original/WebP copyを作り参照DTOを返す]
#   引数: [source: original image path, asset_root: managed asset directory, image_id: stable ID, mode: storage policy]
#   戻り値: [CharacterImage: source provenanceとmanaged pathを持つ登録画像]
# }
def register_character_image(
    source: Path,
    asset_root: Path,
    image_id: str,
    *,
    mode: ImageStorageMode = ImageStorageMode.REFERENCE,
    outfit_id: str | None = None,
    webp_quality: int = 92,
    known_images: tuple[CharacterImage, ...] = (),
) -> CharacterImage:
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise ValueError("image_id must be a safe stable identifier")
    if not 1 <= webp_quality <= 100:
        raise ValueError("webp_quality must be within 1..100")
    unresolved_source = Path(source).expanduser()
    if unresolved_source.is_symlink():
        raise ValueError("character image source must not be a symlink")
    source_path = unresolved_source.resolve(strict=True)
    if not source_path.is_file():
        raise ValueError("character image source must be a regular file")
    mode = ImageStorageMode(mode)
    source_hash = _file_hash(source_path)
    if any(item.sha256 == source_hash for item in known_images):
        raise FileExistsError("duplicate character image content")
    try:
        with Image.open(source_path) as image:
            image.verify()
        with Image.open(source_path) as image:
            dimensions = image.size
            pixels = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("character image is not a readable image") from error

    root = Path(asset_root).expanduser().resolve()
    managed_original = None
    managed_webp = None
    created_targets = []
    if mode is not ImageStorageMode.REFERENCE:
        root.mkdir(parents=True, exist_ok=True)
    try:
        if mode is ImageStorageMode.ORIGINAL_AND_WEBP:
            original_target = root / f"{image_id}{source_path.suffix.lower()}"
            _copy_exclusive(source_path, original_target)
            created_targets.append(original_target)
            managed_original = str(original_target)
        if mode in {ImageStorageMode.MANAGED_WEBP, ImageStorageMode.ORIGINAL_AND_WEBP}:
            webp_target = root / f"{image_id}.webp"
            _save_webp_exclusive(pixels, webp_target, webp_quality)
            created_targets.append(webp_target)
            managed_webp = str(webp_target)
        if _file_hash(source_path) != source_hash:
            raise RuntimeError("character image source changed during registration")
        if managed_original and _file_hash(Path(managed_original)) != source_hash:
            raise RuntimeError("managed original image failed content verification")
    except BaseException:
        for target in created_targets:
            target.unlink(missing_ok=True)
        raise
    return CharacterImage(
        image_id,
        source_path.as_uri(),
        source_hash,
        outfit_id,
        managed_original,
        managed_webp,
        dimensions[0],
        dimensions[1],
    )


# {
#   責務: [preferred_training_image: lossless/high-quality originalをWebPより優先してsourceを返す]
#   処理: [1: managed original/reference sourceの存在を確認する 2: compressed-only時のwarningを添える]
#   引数: [image: registered image]
#   戻り値: [path or uri, warning]
# }
def preferred_training_image(image: CharacterImage) -> tuple[str, str | None]:
    if image.managed_original_uri:
        return image.managed_original_uri, None
    source = image.source_uri
    if source.startswith("file://"):
        source_path = Path(url2pathname(unquote(urlparse(source).path)))
        if source_path.exists():
            return str(source_path), None
    if image.managed_webp_uri:
        return image.managed_webp_uri, "compressed_only_training_source"
    return source, "source_reference_unavailable"


# {
#   責務: [_file_hash: source image contentのSHA-256を計算する]
#   処理: [1: fileをbinary streamで読む 2: content digestを返す]
#   引数: [path: image file]
#   戻り値: [sha256 digest]
# }
def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# {
#   責務: [_copy_exclusive: original imageを既存fileを置換せずmanaged storageへcopyする]
#   処理: [1: exclusive temp copyを作る 2: destination存在を検査する 3: atomic renameする]
#   引数: [source: original path, target: managed copy path]
#   戻り値: []
# }
def _copy_exclusive(source: Path, target: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with source.open("rb") as original, os.fdopen(descriptor, "wb") as staged:
            while chunk := original.read(1024 * 1024):
                staged.write(chunk)
            staged.flush()
            os.fsync(staged.fileno())
        if target.exists():
            raise FileExistsError(target)
        os.link(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


# {
#   責務: [_save_webp_exclusive: normalized pixel imageをWebPへ保存し既存assetを保持する]
#   処理: [1: same-directory temporary WebPを作る 2: decode validatorを確認する 3: exclusive hardlink publishする]
#   引数: [pixels: RGB/RGBA image, target: managed WebP path, quality: encoding quality]
#   戻り値: []
# }
def _save_webp_exclusive(pixels: Image.Image, target: Path, quality: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    try:
        pixels.save(temporary_name, format="WEBP", quality=quality, method=6)
        with Image.open(temporary_name) as staged:
            staged.verify()
        if target.exists():
            raise FileExistsError(target)
        os.link(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
