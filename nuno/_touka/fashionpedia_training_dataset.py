"""Fashionpedia注釈からTouka学習用サンプルを供給するデータセット。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from random import Random

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import Dataset
from torchvision.transforms import functional as transforms

from translucent_surface_augmenter import apply_translucent_surface


# {
# 責務: [FashionpediaTrainingDataset: Fashionpedia annotationsをimage/47-class mask tensor samplesへ変換する]
# フィールド: [dataset_root, image_size, seed, basename-to-image files, filtered annotation samples]
# }
class FashionpediaTrainingDataset(Dataset):
    """通常衣類画像へ半透明素材を合成し、元の分類マスクを正解として返す。"""

    # {
    #   責務: [__init__: dataset paths/configを保存しannotation samples indexを構築する]
    #   処理: [JSON annotation load後imagesを索引しvalid annotated image samplesを決定する]
    #   引数: [self: dataset, dataset_root: Fashionpedia root, image_size: square output dimension, max_samples: optional prefix cap, seed: augmentation seed]
    #   戻り値: [なし]
    #   エラー: [OSError/JSONDecodeError: annotations unreadable]
    #   副作用: [annotation JSONを読み、sample metadataをmemoryへ保持する]
    # }
    def __init__(
        self, dataset_root: Path, image_size: int = 384, max_samples: int = 0, seed: int = 20260830
    ):
        self.dataset_root = Path(dataset_root)
        self.image_size = image_size
        self.seed = seed
        data = self._read_annotations()
        self.files = self._image_files()
        self.samples = self._samples(data, max_samples)

    # {
    #   責務: [_read_annotations: train2020 instances_attributes JSONを読み込む]
    #   処理: [annotations pathをUTF-8でopenしjson.loadを返す]
    #   引数: [self: dataset]
    #   戻り値: [dict: decoded annotation object]
    #   エラー: [OSError/JSONDecodeError: file欠落またはJSON不正]
    #   副作用: [JSON fileを読む]
    # }
    def _read_annotations(self) -> dict:
        path = self.dataset_root / "annotations" / "instances_attributes_train2020.json"
        with path.open(encoding="utf-8") as source:
            return json.load(source)

    # {
    #   責務: [_image_files: train2020 image treeのjpg/jpeg/pngをbasename indexへまとめる]
    #   処理: [recursive directory entriesのfile/suffixだけをfilterする]
    #   引数: [self: dataset]
    #   戻り値: [dict[str,Path]: basename-to-image path mapping]
    # }
    def _image_files(self) -> dict[str, Path]:
        root = self.dataset_root / "images" / "train2020"
        return {
            path.name: path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        }

    # {
    #   責務: [_samples: annotationsをimage ID/file nameでgroupし利用可能なimage samplesにする]
    #   処理: [segmentation listのannotationのみ集めpath解決後basename順にsortしoptional capを適用する]
    #   引数: [self: dataset, data: decoded annotation mapping, max_samples: 0なら全件]
    #   戻り値: [list[(Path, annotations)]: dataset samples]
    # }
    def _samples(self, data: dict, max_samples: int) -> list[tuple[Path, list[dict]]]:
        images = {
            item["id"]: item
            for item in data.get("images", [])
            if isinstance(item, dict) and "id" in item
        }
        grouped: dict[int, list[dict]] = defaultdict(list)
        for annotation in data.get("annotations", []):
            if isinstance(annotation, dict) and isinstance(annotation.get("segmentation"), list):
                grouped[annotation.get("image_id")].append(annotation)
        samples = []
        for image_id, annotations in grouped.items():
            image = images.get(image_id)
            path = self.files.get(image.get("file_name", "")) if image else None
            if path is not None:
                samples.append((path, annotations))
        samples.sort(key=lambda item: item[0].name)
        return samples[:max_samples] if max_samples else samples

    # {
    #   責務: [_mask: instance polygonsを47-class training maskへrasterizeする]
    #   処理: [area昇順でdrawしcategory_id+1をclass labelとして1..46以外を除く]
    #   引数: [self: dataset, size: image dimensions, annotations: image instance annotations]
    #   戻り値: [Pillow L image: background 0とcategory labelを持つmask]
    # }
    def _mask(self, size: tuple[int, int], annotations: list[dict]) -> Image.Image:
        mask = Image.new("L", size, 0)
        drawer = ImageDraw.Draw(mask)
        for annotation in sorted(annotations, key=lambda item: float(item.get("area", 0.0))):
            label = int(annotation.get("category_id", -1)) + 1
            if not 1 <= label <= 46:
                continue
            for polygon in annotation.get("segmentation", []):
                if isinstance(polygon, list) and len(polygon) >= 6:
                    drawer.polygon(
                        [
                            (polygon[index], polygon[index + 1])
                            for index in range(0, len(polygon) - 1, 2)
                        ],
                        fill=label,
                    )
        return mask

    # {
    #   責務: [_tensor_image: RGB imageを正規化済みsquare float tensorへ変換する]
    #   処理: [BILINEAR resize、to_tensor、ImageNet mean/std normalizationを行う]
    #   引数: [self: dataset, image: RGB Pillow image]
    #   戻り値: [torch.Tensor: normalized CHW pixel values]
    # }
    def _tensor_image(self, image: Image.Image) -> torch.Tensor:
        resized = image.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
        return transforms.normalize(
            transforms.to_tensor(resized), mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)
        )

    # {
    #   責務: [_tensor_mask: class maskをnearest resizeしint64 label tensorへ変換する]
    #   処理: [label valuesを保持するためNEAREST resamplingを使う]
    #   引数: [self: dataset, mask: Pillow L label image]
    #   戻り値: [torch.Tensor: HW integer labels]
    # }
    def _tensor_mask(self, mask: Image.Image) -> torch.Tensor:
        resized = mask.resize((self.image_size, self.image_size), Image.Resampling.NEAREST)
        return torch.from_numpy(np.asarray(resized, dtype=np.int64))

    # {
    #   責務: [__len__: indexed training sample数を返す]
    #   処理: [self.samplesの長さを取得する]
    #   引数: [self: dataset]
    #   戻り値: [int: sample count]
    # }
    def __len__(self) -> int:
        return len(self.samples)

    # {
    #   責務: [__getitem__: imageをload/augmentしnormalized pixelsとannotation mask tensorを返す]
    #   処理: [sample pathをRGB decodeしoriginal geometry maskを作ってseed+index RNGでtranslucent surfaceを合成する]
    #   引数: [self: dataset, index: sample index]
    #   戻り値: [dict: pixel_values CHW float tensor, labels HW integer tensor]
    #   エラー: [IndexError/Pillow errors: indexまたはsource image invalid]
    #   副作用: [image fileを読みTorch/NumPy tensorsをmemoryへ作成する]
    # }
    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        path, annotations = self.samples[index]
        with Image.open(path) as source:
            image = source.convert("RGB")
        mask = self._mask(image.size, annotations)
        augmented = apply_translucent_surface(image, Random(self.seed + index))
        return {"pixel_values": self._tensor_image(augmented), "labels": self._tensor_mask(mask)}
