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


class FashionpediaTrainingDataset(Dataset):
    """通常衣類画像へ半透明素材を合成し、元の分類マスクを正解として返す。"""

    def __init__(self, dataset_root: Path, image_size: int = 384, max_samples: int = 0, seed: int = 20260830):
        self.dataset_root = Path(dataset_root)
        self.image_size = image_size
        self.seed = seed
        data = self._read_annotations()
        self.files = self._image_files()
        self.samples = self._samples(data, max_samples)

    def _read_annotations(self) -> dict:
        path = self.dataset_root / "annotations" / "instances_attributes_train2020.json"
        with path.open(encoding="utf-8") as source:
            return json.load(source)

    def _image_files(self) -> dict[str, Path]:
        root = self.dataset_root / "images" / "train2020"
        return {path.name: path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}}

    def _samples(self, data: dict, max_samples: int) -> list[tuple[Path, list[dict]]]:
        images = {item["id"]: item for item in data.get("images", []) if isinstance(item, dict) and "id" in item}
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

    def _mask(self, size: tuple[int, int], annotations: list[dict]) -> Image.Image:
        mask = Image.new("L", size, 0)
        drawer = ImageDraw.Draw(mask)
        for annotation in sorted(annotations, key=lambda item: float(item.get("area", 0.0))):
            label = int(annotation.get("category_id", -1)) + 1
            if not 1 <= label <= 46:
                continue
            for polygon in annotation.get("segmentation", []):
                if isinstance(polygon, list) and len(polygon) >= 6:
                    drawer.polygon([(polygon[index], polygon[index + 1]) for index in range(0, len(polygon) - 1, 2)], fill=label)
        return mask

    def _tensor_image(self, image: Image.Image) -> torch.Tensor:
        resized = image.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
        return transforms.normalize(transforms.to_tensor(resized), mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))

    def _tensor_mask(self, mask: Image.Image) -> torch.Tensor:
        resized = mask.resize((self.image_size, self.image_size), Image.Resampling.NEAREST)
        return torch.from_numpy(np.asarray(resized, dtype=np.int64))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        path, annotations = self.samples[index]
        with Image.open(path) as source:
            image = source.convert("RGB")
        mask = self._mask(image.size, annotations)
        augmented = apply_translucent_surface(image, Random(self.seed + index))
        return {"pixel_values": self._tensor_image(augmented), "labels": self._tensor_mask(mask)}
