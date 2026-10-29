"""Provenance-first image classification and safe cluster copying."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
AI_LABEL = "ai_generated"
NON_AI_LABEL = "non_ai"
UNCERTAIN_LABEL = "uncertain"
CLUSTER_LABELS = {AI_LABEL, NON_AI_LABEL, UNCERTAIN_LABEL}


class ScoreProvider(Protocol):
    # {
    #   責務: [ScoreProvider: 画像判定器のAIスコアAPIを表す]
    #   概要: [本番モデルとテスト用偽物を同じ処理へ注入する]
    # }

    def ai_score(self, path: Path) -> float:
        # {
        #   責務: [ai_score: AI生成ラベルの確率を取得する]
        #   引数: [self: provider, path: 推論対象画像]
        #   戻り値: [0から1までのAI生成スコア]
        # }
        ...


@dataclass(frozen=True)
class ImageOriginResult:
    # {
    #   責務: [ImageOriginResult: 画像単位の判定と証拠を保持する]
    #   概要: [出力クラスタとレビューに必要な情報をまとめる]
    # }

    source_path: Path
    cluster: str
    confidence: float | None
    evidence: tuple[str, ...]
    reason: str
    user_override: bool = False


def discover_images(
    input_root: Path, recursive: bool, excluded_root: Path | None = None
) -> list[Path]:
    # {
    #   責務: [discover_images: 入力root内の対応画像を列挙する]
    #   引数: [input_root: 選択root, recursive: サブフォルダ走査, excluded_root: 出力先]
    #   戻り値: [安定ソートされた画像パス]
    # }
    root = input_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("入力元はフォルダーを指定してください")
    excluded = excluded_root.resolve() if excluded_root else None
    discovered: list[Path] = []
    if recursive:
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name
                for name in directories
                if not (current_path / name).is_symlink()
                and not _is_within(current_path / name, excluded)
            ]
            discovered.extend(
                current_path / name
                for name in filenames
                if (current_path / name).suffix.casefold() in IMAGE_EXTENSIONS
                and not (current_path / name).is_symlink()
            )
    else:
        discovered = [
            path
            for path in root.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.casefold() in IMAGE_EXTENSIONS
        ]
    return sorted(discovered, key=lambda path: str(path).casefold())


def _is_within(path: Path, parent: Path | None) -> bool:
    # {
    #   責務: [_is_within: pathが指定rootの配下か判定する]
    #   引数: [path: 検査パス, parent: 親rootまたはNone]
    #   戻り値: [配下ならTrue]
    # }
    if parent is None:
        return False
    try:
        path.resolve().relative_to(parent)
        return True
    except ValueError:
        return False


def _metadata_signal(metadata: object) -> str | None:
    # {
    #   責務: [_metadata_signal: Pixiv形式metadataから明示的なAI区分を読む]
    #   引数: [metadata: JSON相当の外部値]
    #   戻り値: [ai_generated/non_ai/conflictまたはNone]
    # }
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("aiType", metadata.get("ai_type"))
    if isinstance(value, bool):
        value = None
    signal = AI_LABEL if value in (2, "2") else NON_AI_LABEL if value in (1, "1") else None
    tags = metadata.get("tags", [])
    if isinstance(tags, dict):
        tags = tags.get("tags", [])
    if isinstance(tags, list):
        names = [item.get("tag", "") if isinstance(item, dict) else item for item in tags]
        is_ai_tagged = any(
            isinstance(name, str)
            and name.strip().casefold()
            in {"ai生成", "ai-generated", "ai generated", "aiイラスト", "aiart"}
            for name in names
        )
        if is_ai_tagged:
            return "conflict" if signal == NON_AI_LABEL else AI_LABEL
    return signal


def _read_metadata(path: Path) -> tuple[str | None, str | None]:
    # {
    #   責務: [_read_metadata: sidecarと埋込metadataから判定根拠を読む]
    #   引数: [path: 画像ファイル]
    #   戻り値: [明示信号と根拠名]
    # }
    signals: set[str] = set()
    evidence: list[str] = []
    sidecar = path.with_suffix(".json")
    if sidecar.is_file() and not sidecar.is_symlink():
        try:
            signal = _metadata_signal(json.loads(sidecar.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError):
            return "conflict", "invalid_json_sidecar"
        if signal:
            signals.add(signal)
            evidence.append("pixiv_json_sidecar")

    try:
        from PIL import Image

        with Image.open(path) as image:
            embedded = image.info
            signal = _metadata_signal(embedded)
            if signal:
                signals.add(signal)
                evidence.append("embedded_pixiv_metadata")
            if any(
                key.casefold() in {"parameters", "workflow", "prompt"} and embedded[key]
                for key in embedded
            ):
                signals.add(AI_LABEL)
                evidence.append("embedded_generation_metadata")
    except (OSError, ImportError):
        return "conflict", "image_metadata_read_error"

    if "conflict" in signals or len(signals) > 1:
        return "conflict", ",".join(evidence)
    return (next(iter(signals)), ",".join(evidence)) if signals else (None, None)


def classify_image(
    path: Path,
    score_provider: ScoreProvider,
    low_threshold: float,
    high_threshold: float,
) -> ImageOriginResult:
    # {
    #   責務: [classify_image: 出所metadataを優先して画像を3区分する]
    #   引数: [path: 画像, score_provider: OSS判定器, low_threshold/high_threshold: 判定境界]
    #   戻り値: [判定クラスタ、信頼度、証拠、理由]
    # }
    metadata_label, metadata_evidence = _read_metadata(path)
    if metadata_label == "conflict":
        return ImageOriginResult(
            path,
            UNCERTAIN_LABEL,
            None,
            (metadata_evidence or "metadata_conflict",),
            "metadata_conflict",
        )
    if metadata_label in {AI_LABEL, NON_AI_LABEL}:
        return ImageOriginResult(
            path,
            metadata_label,
            1.0,
            (metadata_evidence or "source_metadata",),
            "explicit_metadata",
        )

    score = score_provider.ai_score(path)
    if score >= high_threshold:
        label, reason = AI_LABEL, "classifier_high_confidence"
    elif score <= low_threshold:
        label, reason = NON_AI_LABEL, "classifier_low_confidence"
    else:
        label, reason = UNCERTAIN_LABEL, "classifier_uncertain"
    return ImageOriginResult(path, label, score, ("oss_classifier",), reason)


def classify_images(
    image_paths: Iterable[Path],
    score_provider: ScoreProvider,
    low_threshold: float = 0.1,
    high_threshold: float = 0.9,
    progress: Callable[[int, int, Path], None] | None = None,
) -> list[ImageOriginResult]:
    # {
    #   責務: [classify_images: 画像一覧を順に判定して結果をまとめる]
    #   引数: [image_paths: 入力画像, score_provider: 判定器, thresholds: 不確実範囲, progress: 進捗通知]
    #   戻り値: [入力順の判定結果]
    # }
    if not 0 <= low_threshold < high_threshold <= 1:
        raise ValueError("しきい値は 0 <= low < high <= 1 にしてください")
    paths = list(image_paths)
    results: list[ImageOriginResult] = []
    for index, path in enumerate(paths, start=1):
        try:
            result = classify_image(path, score_provider, low_threshold, high_threshold)
        except (OSError, ValueError, RuntimeError) as error:
            result = ImageOriginResult(
                path, UNCERTAIN_LABEL, None, ("classifier_error",), str(error)
            )
        results.append(result)
        if progress:
            progress(index, len(paths), path)
    return results


def copy_clusters(results: Iterable[ImageOriginResult], input_root: Path, output_root: Path) -> int:
    # {
    #   責務: [copy_clusters: 判定結果を上書きなしでクラスタ別にコピーする]
    #   引数: [results: 承認済み結果, input_root: 相対パス基準, output_root: 出力先root]
    #   戻り値: [コピーした画像数]
    # }
    source_root = input_root.resolve(strict=True)
    destination_root = output_root.resolve()
    if _is_within(destination_root, source_root) or destination_root == source_root:
        raise ValueError("出力先は入力フォルダーの外に指定してください")
    copied = 0
    for result in results:
        if result.cluster not in CLUSTER_LABELS:
            raise ValueError(f"不明なクラスタです: {result.cluster}")
        relative_path = result.source_path.resolve(strict=True).relative_to(source_root)
        destination = destination_root / result.cluster / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        final_path = _non_overwriting_path(destination)
        _copy_file_atomically(result.source_path, final_path)
        copied += 1
        for extension in (".txt", ".json"):
            sidecar = result.source_path.with_suffix(extension)
            if sidecar.is_file() and not sidecar.is_symlink():
                sidecar_destination = final_path.with_suffix(extension)
                _copy_file_atomically(sidecar, _non_overwriting_path(sidecar_destination))
    return copied


def _non_overwriting_path(path: Path) -> Path:
    # {
    #   責務: [_non_overwriting_path: 既存ファイルを避ける出力名を決める]
    #   引数: [path: 希望する出力パス]
    #   戻り値: [未使用パス。既存ファイルを変更しない]
    # }
    if not path.exists():
        return path
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:10]
    candidate = path.with_name(f"{path.stem}_{digest}{path.suffix}")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{digest}_{index}{path.suffix}")
        index += 1
    return candidate


def _copy_file_atomically(source: Path, destination: Path) -> None:
    # {
    #   責務: [_copy_file_atomically: 一時ファイル経由でコピーを完了する]
    #   引数: [source: コピー元, destination: 上書き禁止のコピー先]
    #   戻り値: []
    # }
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".copying",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copy2(source, temporary)
        if source.stat().st_size != temporary.stat().st_size:
            raise OSError(f"コピー検証に失敗しました: {source}")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_manifest(results: Iterable[ImageOriginResult], manifest_path: Path) -> Path:
    # {
    #   責務: [write_manifest: 判定結果をJSON manifestとして保存する]
    #   引数: [results: 判定結果, manifest_path: 保存先]
    #   戻り値: [保存先。既存manifestを上書きしない]
    # }
    rows = [
        {
            **{
                key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(result).items()
            },
            "evidence": list(result.evidence),
        }
        for result in results
    ]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    final_path = _non_overwriting_path(manifest_path)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{final_path.name}.",
        suffix=".tmp",
        dir=final_path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(json.dumps(rows, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, final_path)
    finally:
        temporary.unlink(missing_ok=True)
    return final_path
