#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FashionpediaからToukaの強調対象参考画像とプリセットを作成する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "user_data" / "input" / "image" / "dataset" / "fashionpedia"
DEFAULT_PRESET_ROOT = PROJECT_ROOT / "user_data" / "input" / "preset" / "touka"
GROUPS = {
    "shirt": {"name": "Fashionpedia_シャツ・ブラウス", "object_preset": "shirt", "category_ids": {0, 1}},
    "clothing": {"name": "Fashionpedia_服・衣類", "object_preset": "clothing", "category_ids": set(range(13))},
    "pants": {"name": "Fashionpedia_パンツ・ショーツ", "object_preset": "panties", "category_ids": {6, 7}},
    "ribbon": {"name": "Fashionpedia_リボン・紐", "object_preset": "ribbon", "category_ids": {16, 25, 41}},
}


def read_annotation(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError(f"注釈JSONの形式が不正です: {path}")
    return data


def image_files(root: Path) -> dict[str, Path]:
    return {path.name: path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}}


def polygon_mask(size: tuple[int, int], segmentation: list, left: int, top: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    drawer = ImageDraw.Draw(mask)
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6:
            continue
        points = [(polygon[index] - left, polygon[index + 1] - top) for index in range(0, len(polygon) - 1, 2)]
        drawer.polygon(points, fill=255)
    return mask


def crop_annotation(image_path: Path, annotation: dict, destination: Path) -> bool:
    segmentation = annotation.get("segmentation")
    bbox = annotation.get("bbox")
    if not isinstance(segmentation, list) or not isinstance(bbox, list) or len(bbox) != 4:
        return False
    with Image.open(image_path) as image:
        image = image.convert("RGBA")
        x, y, width, height = (float(value) for value in bbox)
        left = max(0, int(x)); top = max(0, int(y))
        right = min(image.width, max(left + 1, int(x + width + 0.999)))
        bottom = min(image.height, max(top + 1, int(y + height + 0.999)))
        cropped = image.crop((left, top, right, bottom))
        mask = polygon_mask(cropped.size, segmentation, left, top)
        if mask.getbbox() is None:
            return False
        cropped.putalpha(mask)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(destination)
    return True


def build_group(group_key: str, group: dict, annotations: list, images: dict[int, dict], files: dict[str, Path], reference_root: Path, limit: int) -> int:
    destination = reference_root / group_key
    category_ids = group["category_ids"]
    count = 0
    for annotation in annotations:
        if annotation.get("category_id") not in category_ids:
            continue
        image_info = images.get(annotation.get("image_id"))
        image_path = files.get(image_info.get("file_name", "")) if image_info else None
        if image_path is None:
            continue
        output = destination / f"{annotation.get('id', count)}.png"
        if output.is_file() or crop_annotation(image_path, annotation, output):
            count += 1
        if count >= limit:
            break
    return count


def preset_values(group: dict, reference_dir: Path) -> dict:
    return {
        "mode": "video",
        "profile": "balanced",
        "object_preset": next(label for label, value in {"服・衣類": "clothing", "シャツ・ブラウス": "shirt", "ショーツ・パンツ": "panties", "リボン・紐": "ribbon"}.items() if value == group["object_preset"]),
        "surface_preset": "自動推定",
        "cpu_cores": "",
        "preview_seconds": "5",
        "preview_start_seconds": "0",
        "roi": "",
        "input_path": "",
        "output_path": "",
        "reference_path": str(reference_dir),
        "surface_reference_path": "",
    }


def write_preset(preset_root: Path, group: dict, reference_dir: Path) -> Path:
    path = preset_root / f"{group['name']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preset_values(group, reference_dir), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build(dataset_root: Path, preset_root: Path, limit: int) -> list[tuple[str, int, Path]]:
    annotation_path = dataset_root / "annotations" / "instances_attributes_train2020.json"
    image_root = dataset_root / "images" / "train2020"
    if not annotation_path.is_file():
        raise FileNotFoundError(f"学習注釈が見つかりません: {annotation_path}")
    if not image_root.is_dir():
        raise FileNotFoundError(f"学習画像フォルダが見つかりません: {image_root}")
    data = read_annotation(annotation_path)
    files = image_files(image_root)
    if not files:
        raise FileNotFoundError(f"学習画像が見つかりません: {image_root}")
    images = {item["id"]: item for item in data.get("images", []) if isinstance(item, dict) and "id" in item}
    annotations = [item for item in data.get("annotations", []) if isinstance(item, dict)]
    reference_root = preset_root / "reference" / "fashionpedia"
    result = []
    for key, group in GROUPS.items():
        count = build_group(key, group, annotations, images, files, reference_root, limit)
        preset_path = write_preset(preset_root, group, reference_root / key)
        result.append((key, count, preset_path))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FashionpediaからToukaプリセットを作成")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--preset-root", type=Path, default=DEFAULT_PRESET_ROOT)
    parser.add_argument("--limit", type=int, default=48, help="各分類の参考画像上限")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise ValueError("--limit は1以上で指定してください")
    for key, count, preset_path in build(args.dataset_root, args.preset_root, args.limit):
        print(f"{key}: {count}件 / {preset_path}", flush=True)


if __name__ == "__main__":
    main()
