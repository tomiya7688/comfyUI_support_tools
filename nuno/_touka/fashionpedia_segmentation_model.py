"""Touka用Fashionpediaセグメンテーションモデルの生成と保存。"""

from __future__ import annotations

import json
import os
from pathlib import Path


CLASS_COUNT = 47
MODEL_NAME = "fashionpedia_deeplabv3_mobilenetv3"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_model_dir() -> Path:
    return project_root() / "user_data" / "input" / "models" / "touka" / MODEL_NAME


def configure_torch_cache() -> Path:
    cache = project_root() / "user_data" / "input" / "models" / "touka" / "torch_cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TORCH_HOME", str(cache))
    return cache


def create_model(pretrained: bool = True):
    configure_torch_cache()
    from torch import nn
    from torchvision.models import MobileNet_V3_Large_Weights
    from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large

    backbone_weights = MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
    model = deeplabv3_mobilenet_v3_large(weights=None, weights_backbone=backbone_weights)
    model.classifier[-1] = nn.Conv2d(model.classifier[-1].in_channels, CLASS_COUNT, kernel_size=1)
    if model.aux_classifier is not None:
        model.aux_classifier[-1] = nn.Conv2d(model.aux_classifier[-1].in_channels, CLASS_COUNT, kernel_size=1)
    return model


def save_model(model, directory: Path, metadata: dict) -> Path:
    import torch

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.pt"
    torch.save({"model_state": model.state_dict(), "class_count": CLASS_COUNT}, path)
    (directory / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_model(directory: Path, device):
    import torch

    checkpoint = torch.load(Path(directory) / "model.pt", map_location=device, weights_only=True)
    if checkpoint.get("class_count") != CLASS_COUNT:
        raise ValueError("Fashionpediaモデルの分類数が一致しません")
    model = create_model(pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    return model.to(device).eval()
