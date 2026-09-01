#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fashionpedia注釈をDeepLabV3学習用の意味マスクとして提供するDataset。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import Dataset
from torchvision.transforms import functional as transforms


class FashionpediaSegmentationDataset(Dataset):
    """Fashionpedia画像と46カテゴリ+背景の意味マスクを返す。"""

    def __init__(self, annotation_path: Path, image_root: Path, image_size: int = 384):
        self.image_size = int(image_size)
        if self.image_size <= 0:
            raise ValueError("image_size は1以上で指定してください")
        data = self._read_annotation(annotation_path)
        self.records = self._build_records(data, image_root)
        if not self.records:
            raise FileNotFoundError(f"注釈に対応する画像がありません: {image_root}")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image_path, annotations = self.records[index]
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        mask = self._semantic_mask(image.size, annotations)
        image = transforms.resize(image, [self.image_size, self.image_size], antialias=True)
        mask = transforms.resize(mask, [self.image_size, self.image_size], interpolation=Image.Resampling.NEAREST)
        return transforms.to_tensor(image), torch.from_numpy(np.asarray(mask, dtype="int64").copy())

    def _read_annotation(self, path: Path) -> dict:
        with Path(path).open(encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict):
            raise ValueError(f"注釈JSONの形式が不正です: {path}")
        return data

    def _build_records(self, data: dict, image_root: Path) -> list[tuple[Path, list[dict]]]:
        annotations = defaultdict(list)
        for annotation in data.get("annotations", []):
            if isinstance(annotation, dict) and isinstance(annotation.get("image_id"), int):
                annotations[annotation["image_id"]].append(annotation)
        files = {path.name: path for path in Path(image_root).rglob("*") if path.is_file()}
        records = []
        for image in data.get("images", []):
            if not isinstance(image, dict):
                continue
            image_id = image.get("id")
            image_path = files.get(image.get("file_name", ""))
            if image_id in annotations and image_path is not None:
                records.append((image_path, annotations[image_id]))
        return records

    def _semantic_mask(self, size: tuple[int, int], annotations: list[dict]) -> Image.Image:
        mask = Image.new("L", size, 0)
        drawer = ImageDraw.Draw(mask)
        for annotation in annotations:
            category_id = annotation.get("category_id")
            segmentation = annotation.get("segmentation")
            if not isinstance(category_id, int) or not 0 <= category_id < 46 or not isinstance(segmentation, list):
                continue
            for polygon in segmentation:
                if not isinstance(polygon, list) or len(polygon) < 6:
                    continue
                drawer.polygon([(polygon[position], polygon[position + 1]) for position in range(0, len(polygon) - 1, 2)], fill=category_id + 1)
        return mask
