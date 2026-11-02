"""Touka用Fashionpediaセグメンテーションモデルの生成と保存。"""

from __future__ import annotations

import json
import os
from pathlib import Path


CLASS_COUNT = 47
MODEL_NAME = "fashionpedia_deeplabv3_mobilenetv3"


# {
#   責務: [project_root: package checkout rootを返す]
#   処理: [このsource fileから2 parent上のPathを解決する]
#   引数: []
#   戻り値: [Path: project root]
# }
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


# {
#   責務: [default_model_dir: Fashionpedia segmentation checkpointのdefault directoryを作る]
#   処理: [project user_data model root下へMODEL_NAMEを付ける]
#   引数: []
#   戻り値: [Path: checkpoint directory path]
# }
def default_model_dir() -> Path:
    return project_root() / "user_data" / "input" / "models" / "touka" / MODEL_NAME


# {
#   責務: [configure_torch_cache: project内Torch download cache directoryを準備する]
#   処理: [directoryを作成しTORCH_HOMEが未設定の場合のみ環境変数を設定する]
#   引数: []
#   戻り値: [Path: torch cache directory]
#   副作用: [filesystem directoryとprocess environmentを必要に応じて更新する]
# }
def configure_torch_cache() -> Path:
    cache = project_root() / "user_data" / "input" / "models" / "touka" / "torch_cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TORCH_HOME", str(cache))
    return cache


# {
#   責務: [create_model: 47-class DeepLabV3 MobileNetV3 segmentation modelを生成する]
#   処理: [cacheを準備しoptional backbone weightsでmodelを作りmain/aux classifier outputを47 channelにする]
#   引数: [pretrained: torchvision backbone DEFAULT weightsを使うか]
#   戻り値: [torchvision segmentation model]
#   副作用: [pretrained時torchvision weight cacheを参照/必要に応じdownloadする]
# }
def create_model(pretrained: bool = True):
    configure_torch_cache()
    from torch import nn
    from torchvision.models import MobileNet_V3_Large_Weights
    from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large

    backbone_weights = MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
    model = deeplabv3_mobilenet_v3_large(weights=None, weights_backbone=backbone_weights)
    model.classifier[-1] = nn.Conv2d(model.classifier[-1].in_channels, CLASS_COUNT, kernel_size=1)
    if model.aux_classifier is not None:
        model.aux_classifier[-1] = nn.Conv2d(
            model.aux_classifier[-1].in_channels, CLASS_COUNT, kernel_size=1
        )
    return model


# {
#   責務: [save_model: model stateとclass countをcheckpoint、metadataをJSONとして保存する]
#   処理: [directoryを作りmodel.ptとmetadata.jsonを書き込む]
#   引数: [model: torch model, directory: destination directory, metadata: JSON-compatible metadata]
#   戻り値: [Path: model.pt checkpoint path]
#   副作用: [directoryとcheckpoint/metadata filesを作成または上書きする]
# }
def save_model(model, directory: Path, metadata: dict) -> Path:
    import torch

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "model.pt"
    torch.save({"model_state": model.state_dict(), "class_count": CLASS_COUNT}, path)
    (directory / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


# {
#   責務: [load_model: weights-only checkpointを指定deviceへ読みclassifier shapeを検証する]
#   処理: [class_countを47と照合しnon-pretrained architectureへstate_dictをloadしてeval modeにする]
#   引数: [directory: model checkpoint directory, device: torch map_location/device]
#   戻り値: [torch model: device上のevaluation model]
#   エラー: [ValueError: class count不一致, torch.load/load_state_dict errors]
#   副作用: [checkpoint fileをdiskから読む。modelをVRAMまたはdevice memoryへ移す]
# }
def load_model(directory: Path, device):
    import torch

    checkpoint = torch.load(Path(directory) / "model.pt", map_location=device, weights_only=True)
    if checkpoint.get("class_count") != CLASS_COUNT:
        raise ValueError("Fashionpediaモデルの分類数が一致しません")
    model = create_model(pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    return model.to(device).eval()
