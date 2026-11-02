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
    "shirt": {
        "name": "Fashionpedia_シャツ・ブラウス",
        "object_preset": "shirt",
        "category_ids": {0, 1},
    },
    "clothing": {
        "name": "Fashionpedia_服・衣類",
        "object_preset": "clothing",
        "category_ids": set(range(13)),
    },
    "pants": {
        "name": "Fashionpedia_パンツ・ショーツ",
        "object_preset": "panties",
        "category_ids": {6, 7},
    },
    "ribbon": {
        "name": "Fashionpedia_リボン・紐",
        "object_preset": "ribbon",
        "category_ids": {16, 25, 41},
    },
}


# {
#   責務: [read_annotation: UTF-8 Fashionpedia annotation JSONをobjectとして読み込む]
#   処理: [json.load後rootがdictであることを検証する]
#   引数: [path: annotation JSON path]
#   戻り値: [dict: decoded annotation object]
#   エラー: [ValueError: rootがobjectでない, OSError/JSONDecodeError: 読込/parse失敗]
#   副作用: [JSON fileを読み取る]
# }
def read_annotation(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError(f"注釈JSONの形式が不正です: {path}")
    return data


# {
#   責務: [image_files: dataset treeから対応する画像fileをbasename keyで索引化する]
#   処理: [recursive filesのjpg/jpeg/png/webp suffixをcase-insensitiveに選ぶ]
#   引数: [root: image directory]
#   戻り値: [dict[str,Path]: basenameから画像pathへのmapping]
# }
def image_files(root: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    }


# {
#   責務: [polygon_mask: segmentation polygonsをcrop-local grayscale maskへ描く]
#   処理: [各有効polygonの座標からcrop originを引きfill 255で塗る]
#   引数: [size: crop width/height, segmentation: polygon coordinate lists, left/top: source crop origin]
#   戻り値: [Pillow L image: binary-like object mask]
# }
def polygon_mask(size: tuple[int, int], segmentation: list, left: int, top: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    drawer = ImageDraw.Draw(mask)
    for polygon in segmentation:
        if not isinstance(polygon, list) or len(polygon) < 6:
            continue
        points = [
            (polygon[index] - left, polygon[index + 1] - top)
            for index in range(0, len(polygon) - 1, 2)
        ]
        drawer.polygon(points, fill=255)
    return mask


# {
#   責務: [crop_annotation: imageとannotation polygonから透過背景reference cropを生成する]
#   処理: [bboxをimage boundsへclipしmask-empty/invalid annotationはfalse、成功時PNGを保存する]
#   引数: [image_path: source image, annotation: bbox/segmentation mapping, destination: output PNG path]
#   戻り値: [bool: reference cropが生成または無効でない場合true]
#   副作用: [source imageを読み、destination parentを作りPNGを書き込む]
#   エラー: [Pillow/filesystem errorsは呼出元へ伝播する]
# }
def crop_annotation(image_path: Path, annotation: dict, destination: Path) -> bool:
    segmentation = annotation.get("segmentation")
    bbox = annotation.get("bbox")
    if not isinstance(segmentation, list) or not isinstance(bbox, list) or len(bbox) != 4:
        return False
    with Image.open(image_path) as image:
        image = image.convert("RGBA")
        x, y, width, height = (float(value) for value in bbox)
        left = max(0, int(x))
        top = max(0, int(y))
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


# {
#   責務: [build_group: 指定カテゴリgroupのreference cropsをlimit件まで作る]
#   処理: [category IDをfilterしimage ID/file nameをresolve、existing PNGをcountし必要なcropを保存する]
#   引数: [group_key/group: group identity/settings, annotations: instance records, images/files: lookup maps, reference_root: destination root, limit: maximum accepted items]
#   戻り値: [int: existing/generated reference PNG count]
#   副作用: [group folder以下へPNG cropを作成する]
# }
def build_group(
    group_key: str,
    group: dict,
    annotations: list,
    images: dict[int, dict],
    files: dict[str, Path],
    reference_root: Path,
    limit: int,
) -> int:
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


# {
#   責務: [preset_values: group用Touka video preset mappingを参照directory付きで作る]
#   処理: [object preset labelをgroup keyから対応表で選び他のvideo mode defaultsを設定する]
#   引数: [group: GROUPS entry, reference_dir: generated crop folder]
#   戻り値: [dict[str,str]: preset storeが保存するfield values]
#   エラー: [StopIteration: object_presetがlabel mappingにない]
# }
def preset_values(group: dict, reference_dir: Path) -> dict:
    return {
        "mode": "video",
        "profile": "balanced",
        "object_preset": next(
            label
            for label, value in {
                "服・衣類": "clothing",
                "シャツ・ブラウス": "shirt",
                "ショーツ・パンツ": "panties",
                "リボン・紐": "ribbon",
            }.items()
            if value == group["object_preset"]
        ),
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


# {
#   責務: [write_preset: preset valuesをnamed UTF-8 JSON fileとして保存する]
#   処理: [group nameからpathを作りindent付きJSONとnewlineを書く]
#   引数: [preset_root: destination root, group: GROUPS entry, reference_dir: reference image directory]
#   戻り値: [Path: 書き込んだpreset file]
#   副作用: [parent directoryを作成しpreset JSONを新規作成または上書きする]
# }
def write_preset(preset_root: Path, group: dict, reference_dir: Path) -> Path:
    path = preset_root / f"{group['name']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(preset_values(group, reference_dir), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


# {
#   責務: [build: Fashionpedia training annotation/image treeから全group cropとpresetを作る]
#   処理: [required paths確認、JSON/index load後4 GROUPSを処理しpreset/reference countを返す]
#   引数: [dataset_root: dataset directory, preset_root: generated outputs root, limit: per-group crop maximum]
#   戻り値: [list[(group key, crop count, preset path)]]
#   エラー: [FileNotFoundError: annotation/image folder or files missing]
#   副作用: [annotation JSONとdataset imagesを読み、reference PNG/preset JSONを書き込む]
# }
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
    images = {
        item["id"]: item
        for item in data.get("images", [])
        if isinstance(item, dict) and "id" in item
    }
    annotations = [item for item in data.get("annotations", []) if isinstance(item, dict)]
    reference_root = preset_root / "reference" / "fashionpedia"
    result = []
    for key, group in GROUPS.items():
        count = build_group(key, group, annotations, images, files, reference_root, limit)
        preset_path = write_preset(preset_root, group, reference_root / key)
        result.append((key, count, preset_path))
    return result


# {
#   責務: [parse_args: dataset/preset rootsとper-group limit CLI optionsを定義する]
#   処理: [argparse defaultsをmodule default paths/48 samplesへ設定する]
#   引数: []
#   戻り値: [argparse.Namespace: parsed command-line options]
# }
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FashionpediaからToukaプリセットを作成")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--preset-root", type=Path, default=DEFAULT_PRESET_ROOT)
    parser.add_argument("--limit", type=int, default=48, help="各分類の参考画像上限")
    return parser.parse_args()


# {
#   責務: [main: CLI argsを検証しFashionpedia crop/preset buildを実行して件数を表示する]
#   処理: [positive limitを要求しgroup resultをflush付きstdoutへ出力する]
#   引数: []
#   戻り値: [None]
#   エラー: [ValueError: limitが1未満, buildが返すfilesystem/JSON errors]
#   副作用: [reference image/preset filesを作成しstdoutへ書く]
# }
def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise ValueError("--limit は1以上で指定してください")
    for key, count, preset_path in build(args.dataset_root, args.preset_root, args.limit):
        print(f"{key}: {count}件 / {preset_path}", flush=True)


if __name__ == "__main__":
    main()
