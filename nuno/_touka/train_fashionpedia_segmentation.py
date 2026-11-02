#!/usr/bin/env python3
"""半透明素材を合成したFashionpediaデータでToukaモデルを学習する。"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Subset

from fashionpedia_segmentation_model import MODEL_NAME, default_model_dir, save_model, create_model
from fashionpedia_training_dataset import FashionpediaTrainingDataset


# {
#   責務: [parse_args: Fashionpedia segmentation training configuration CLIを解析する]
#   処理: [dataset/model paths、epochs/batch/image/sample/LR/validation、pretrained toggleを設定する]
#   引数: []
#   戻り値: [argparse.Namespace: training options]
# }
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Touka Fashionpedia segmentation training")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "user_data"
        / "input"
        / "image"
        / "dataset"
        / "fashionpedia",
    )
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--image-size", type=int, default=384)
    parser.add_argument("--max-samples", type=int, default=0, help="0なら全画像を使う")
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--no-pretrained", action="store_true")
    return parser.parse_args()


# {
#   責務: [validate_args: epochs/batch/image sizeとvalidation split ratioの最低条件を検証する]
#   処理: [positive epochs/batch、image_size>=128、0<validation_ratio<0.5を要求する]
#   引数: [args: parsed training options]
#   戻り値: [None]
#   エラー: [ValueError: option valuesがtraining constraintsに違反]
# }
def validate_args(args: argparse.Namespace) -> None:
    if args.epochs <= 0 or args.batch_size <= 0 or args.image_size < 128:
        raise ValueError("epochs、batch-sizeは1以上、image-sizeは128以上で指定してください")
    if not 0.0 < args.validation_ratio < 0.5:
        raise ValueError("validation-ratioは0より大きく0.5未満で指定してください")


# {
#   責務: [split_indices: 固定seedでsample indicesをshuffleしtrain/validation subsetsを分ける]
#   処理: [validation countを最低1にし先頭をvalidationへ割り当てる]
#   引数: [count: dataset samples, ratio: validation fraction]
#   戻り値: [(train indices, validation indices)]
#   エラー: [ValueError: 2未満のsample count]
# }
def split_indices(count: int, ratio: float) -> tuple[list[int], list[int]]:
    if count < 2:
        raise ValueError("学習には有効な画像が2枚以上必要です")
    indices = list(range(count))
    random.Random(20260830).shuffle(indices)
    validation_count = max(1, round(count * ratio))
    return indices[validation_count:], indices[:validation_count]


# {
#   責務: [loader: index subsetに対するDataLoaderを構築する]
#   処理: [shuffle optionを適用しworker count 0、CUDA available時だけpin_memoryを使う]
#   引数: [dataset: Fashionpedia dataset, indices: subset indices, batch_size: batch dimension, shuffle: randomized order flag]
#   戻り値: [DataLoader: requested subset loader]
# }
def loader(dataset, indices: list[int], batch_size: int, shuffle: bool) -> DataLoader:
    return DataLoader(
        Subset(dataset, indices),
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
    )


# {
#   責務: [batch_loss: batch tensorsをdeviceへ送りsegmentation logitsのcross entropyを計算する]
#   処理: [pixel_values/labelsをnon-blocking transferしmodel outへcriterionを適用する]
#   引数: [model: segmentation model, batch: tensor mapping, criterion: loss module, device: torch device]
#   戻り値: [torch.Tensor: differentiable batch loss]
#   副作用: [GPU device時activation/logitsをVRAMへ置きforwardを実行する]
# }
def batch_loss(model, batch: dict, criterion, device) -> torch.Tensor:
    pixels = batch["pixel_values"].to(device, non_blocking=True)
    labels = batch["labels"].to(device, non_blocking=True)
    logits = model(pixels)["out"]
    return criterion(logits, labels)


# {
#   責務: [freeze_batch_norm: BatchNorm modulesをevaluation modeに保ちrunning statistics updateを止める]
#   処理: [model.modulesを走査し_BatchNorm instanceのevalを呼ぶ]
#   引数: [model: torch.nn module]
#   戻り値: [None]
#   副作用: [BatchNorm submodule training flagsを変更する]
# }
def freeze_batch_norm(model) -> None:
    for module in model.modules():
        if isinstance(module, nn.modules.batchnorm._BatchNorm):
            module.eval()


# {
#   責務: [train_epoch: batchesをforward/backward/AdamW updateしmean training lossを返す]
#   処理: [model train、BatchNorm freeze、gradient reset/loss backward/optimizer stepを反復する]
#   引数: [model: segmentation model, batches: DataLoader, optimizer: optimizer, criterion: loss module, device: compute device]
#   戻り値: [float: batch mean loss。empty batchesなら0]
#   副作用: [model weightsを更新しGPU使用時VRAMへactivations/gradientsを配置する]
# }
def train_epoch(model, batches, optimizer, criterion, device) -> float:
    model.train()
    freeze_batch_norm(model)
    total = 0.0
    for batch in batches:
        optimizer.zero_grad(set_to_none=True)
        loss = batch_loss(model, batch, criterion, device)
        loss.backward()
        optimizer.step()
        total += float(loss.detach().cpu())
    return total / max(1, len(batches))


# {
#   責務: [validation_loss: eval/no_grad modeでvalidation batchesのmean lossを計算する]
#   処理: [各batchのlossをCPU scalarへ移して平均する]
#   引数: [model: segmentation model, batches: validation DataLoader, criterion: loss module, device: compute device]
#   戻り値: [float: validation mean loss。empty batchesなら0]
#   副作用: [forwardを実行するがweight/gradientは更新しない]
# }
def validation_loss(model, batches, criterion, device) -> float:
    model.eval()
    total = 0.0
    with torch.no_grad():
        for batch in batches:
            total += float(batch_loss(model, batch, criterion, device).detach().cpu())
    return total / max(1, len(batches))


# {
#   責務: [main: CLI設定に従いFashionpedia modelをtrainしcheckpointとmetadataを保存する]
#   処理: [dataset/split/loaders/model/AdamW/CrossEntropyを準備しepoch loop後save_modelを呼ぶ]
#   引数: []
#   戻り値: [None]
#   エラー: [ValueError: args/sample count invalid, dataset/model/filesystem/torch errors]
#   副作用: [dataset imagesを読む、CPU/GPU memoryを使ってtraining、CUDA時VRAMを使用、model.pt/metadata.jsonを保存しstdoutへ進捗出力]
# }
def main() -> None:
    args = parse_args()
    validate_args(args)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = FashionpediaTrainingDataset(
        args.dataset_root, image_size=args.image_size, max_samples=args.max_samples
    )
    train_indices, validation_indices = split_indices(len(dataset), args.validation_ratio)
    train_batches = loader(dataset, train_indices, args.batch_size, True)
    validation_batches = loader(dataset, validation_indices, args.batch_size, False)
    model = create_model(pretrained=not args.no_pretrained).to(device)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()
    history = []
    for epoch in range(1, args.epochs + 1):
        dataset.seed = 20260830 + epoch * max(1, len(dataset))
        train_loss = train_epoch(model, train_batches, optimizer, criterion, device)
        validation = validation_loss(model, validation_batches, criterion, device)
        history.append({"epoch": epoch, "train_loss": train_loss, "validation_loss": validation})
        print(
            f"epoch={epoch} train_loss={train_loss:.5f} validation_loss={validation:.5f}",
            flush=True,
        )
    metadata = {
        "name": MODEL_NAME,
        "architecture": "DeepLabV3 MobileNetV3 Large",
        "dataset": "Fashionpedia 46 classes + background",
        "device": str(device),
        "image_size": args.image_size,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "pretrained": not args.no_pretrained,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "history": history,
    }
    model_path = save_model(model, args.model_dir, metadata)
    print(
        json.dumps(
            {"model": str(model_path), "metadata": str(args.model_dir / "metadata.json")},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
