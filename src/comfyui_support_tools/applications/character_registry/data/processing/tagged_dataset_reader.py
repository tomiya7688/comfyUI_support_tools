from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
MANIFEST_NAME = "manifest.json"


# {
#   責務: [_load_manifest: intake datasetのsource manifestを検証して読み込む]
#   処理: [manifest.jsonのassets配列を読み, caption_fileをkeyにしたprovenance mappingを返す]
#   引数: [manifest_path: manifest.json path]
#   戻り値: [tuple[dict[str, dict[str, str]], list[str]]: metadata mappingと警告]
#   エラー: [ValueError: JSONまたはassets構造が不正な場合]
# }
def _load_manifest(manifest_path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    if not manifest_path.is_file():
        return {}, ["manifest.jsonがありません。source/license情報はunknownとして扱います。"]
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"manifest.jsonを読み込めません: {error}") from error
    assets = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list):
        raise ValueError("manifest.jsonのassetsは配列である必要があります")
    indexed: dict[str, dict[str, str]] = {}
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("caption_file"), str):
            raise ValueError("manifest assetにはcaption_file文字列が必要です")
        caption_file = _safe_relative_path(item["caption_file"], "caption_file")
        if caption_file in indexed:
            raise ValueError(f"manifestにcaption_fileの重複があります: {caption_file}")
        image_file = item.get("image_file", "")
        if image_file is not None and not isinstance(image_file, str):
            raise ValueError("manifestのimage_fileは文字列またはnullである必要があります")
        if image_file:
            image_file = _safe_relative_path(image_file, "image_file")
        indexed[caption_file] = {
            key: (image_file if key == "image_file" else str(item.get(key) or "").strip())
            for key in (
                "image_file",
                "source_url",
                "source_work_id",
                "license_status",
                "training_permission",
            )
        }
    return indexed, []


# {
#   責務: [_safe_relative_path: manifest file referenceをdataset内相対pathへ制限する]
#   処理: [absolute path, drive path, parent traversalを拒否しnormalized POSIX pathを返す]
#   引数: [value: manifest内path, field_name: エラー表示用field名]
#   戻り値: [str: dataset rootからの安全な相対path]
#   エラー: [ValueError: 空pathまたはdataset外を参照する場合]
# }
def _safe_relative_path(value: str, field_name: str) -> str:
    normalized_text = value.replace("\\", "/")
    posix_path = PurePosixPath(normalized_text)
    windows_path = PureWindowsPath(value)
    if not value.strip() or posix_path.is_absolute() or windows_path.drive or windows_path.root:
        raise ValueError(f"manifestの{field_name}はdataset内の相対pathにしてください")
    if not posix_path.parts or posix_path == PurePosixPath(".") or ".." in posix_path.parts:
        raise ValueError(f"manifestの{field_name}に不正なpath要素があります")
    return posix_path.as_posix()


# {
#   責務: [_is_inside_dataset: 解決済みpathがdataset root内にあるか判定する]
#   処理: [symlinkを解決したpathからrootへの相対path化を試し, 範囲外ならfalseを返す]
#   引数: [dataset_root: 読取を許可されたroot, candidate: 検査path]
#   戻り値: [bool: candidateがdataset root内に収まる場合true]
# }
def _is_inside_dataset(dataset_root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(dataset_root.resolve())
    except (OSError, ValueError):
        return False
    return True


# {
#   責務: [_index_images: 1つのcaption directoryにある画像をstem/拡張子でindex化する]
#   処理: [1: image fileを順番に走査する, 2: stemとcasefold suffixでmappingを返す]
#   引数: [directory: 画像を探すdirectory]
#   戻り値: [dict[tuple[str, str], Path]: 正規化stemとsuffixから画像pathを得るindex]
# }
def _index_images(directory: Path) -> dict[tuple[str, str], Path]:
    image_index: dict[tuple[str, str], Path] = {}
    for candidate in sorted(
        directory.iterdir(), key=lambda path: (path.name.casefold(), path.name)
    ):
        suffix = candidate.suffix.casefold()
        if candidate.is_file() and suffix in IMAGE_SUFFIXES:
            image_index.setdefault((candidate.stem.casefold(), suffix), candidate)
    return image_index


# {
#   責務: [_find_image: captionと同名の画像をdataset内から探す]
#   処理: [caption stemとimage indexを照合し, 設定された拡張子優先順でpathを返す]
#   引数: [caption: caption file path, image_index: 親directoryの画像index]
#   戻り値: [Path | None: 画像が存在する場合の相対path]
# }
def _find_image(caption: Path, image_index: dict[tuple[str, str], Path]) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        image = image_index.get((caption.stem.casefold(), suffix.casefold()))
        if image:
            return image
    return None


# {
#   責務: [read_tagged_dataset: sidecar captionとprovenance manifestをsource assetへ変換する]
#   処理: [1: manifest範囲を検証して読む, 2: captionとimageの安全な参照だけを走査する, 3: provenanceを保持したassetへ変換する]
#   引数: [dataset_root: identity/とoutfits/を含むdataset root]
#   戻り値: [tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]: asset一覧とwarning]
#   エラー: [ValueError: dataset rootまたはcaption/manifest形式が不正な場合]
# }
def read_tagged_dataset(
    dataset_root: Path,
) -> tuple[tuple[CharacterSourceAsset, ...], tuple[str, ...]]:
    """Read sidecar tag files and keep their source metadata attached."""
    if not dataset_root.is_dir():
        raise ValueError(f"tagged dataset directoryがありません: {dataset_root}")
    manifest_path = dataset_root / MANIFEST_NAME
    if not _is_inside_dataset(dataset_root, manifest_path):
        raise ValueError("manifest.jsonはdataset root外を参照できません")
    manifest, warnings = _load_manifest(manifest_path)
    caption_files = sorted(
        (path for path in dataset_root.rglob("*.txt") if path.name.lower() != MANIFEST_NAME),
        key=lambda path: path.as_posix().casefold(),
    )
    result: list[CharacterSourceAsset] = []
    image_indexes: dict[Path, dict[tuple[str, str], Path]] = {}
    for caption in caption_files:
        if not _is_inside_dataset(dataset_root, caption):
            warnings.append(f"dataset外を指すcaption symlinkを除外しました: {caption}")
            continue
        relative = caption.relative_to(dataset_root).as_posix()
        try:
            caption_text = caption.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"captionを読み込めません: {relative}: {error}") from error
        tags = tuple(dict.fromkeys(tag.strip() for tag in caption_text.split(",") if tag.strip()))
        if not tags:
            warnings.append(f"空captionを除外しました: {relative}")
            continue
        metadata = manifest.get(relative, {})
        if caption.parent not in image_indexes:
            image_indexes[caption.parent] = _index_images(caption.parent)
        image_path = _find_image(caption, image_indexes[caption.parent])
        image = metadata.get("image_file") or (
            image_path.relative_to(dataset_root).as_posix() if image_path else ""
        )
        resolved_image = dataset_root / image if image else None
        if image and (
            resolved_image is None
            or not _is_inside_dataset(dataset_root, resolved_image)
            or not resolved_image.is_file()
        ):
            warnings.append(f"dataset内に安全な画像fileが見つかりません: {relative} -> {image}")
            image = ""
        if not image:
            warnings.append(f"画像がないcaptionです: {relative}")
        parts = Path(relative).parts
        outfit_id = parts[1] if len(parts) > 2 and parts[0].casefold() == "outfits" else None
        if relative not in manifest:
            warnings.append(f"manifestにsource情報がありません: {relative}")
        result.append(
            CharacterSourceAsset(
                caption_file=relative,
                image_file=image or None,
                tags=tags,
                outfit_id=outfit_id,
                source_url=metadata.get("source_url", ""),
                source_work_id=metadata.get("source_work_id", ""),
                license_status=metadata.get("license_status") or "unknown",
                training_permission=metadata.get("training_permission") or "unknown",
            )
        )
    if not result:
        warnings.append("解析可能なcaption fileがありません")
    return tuple(result), tuple(dict.fromkeys(warnings))
