"""Provenance-first image classification and safe cluster copying."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AI_LABEL = "ai_generated"
NON_AI_LABEL = "non_ai"
UNCERTAIN_LABEL = "uncertain"
CLUSTER_LABELS = {AI_LABEL, NON_AI_LABEL, UNCERTAIN_LABEL}
_MANIFEST_LOCK = threading.Lock()


# {
# 責務: [ScoreProvider: 画像判定器のAIスコアAPIを表す]
# フィールド: [状態: 画像判定器のAIスコアAPIを表す]
# }
class ScoreProvider(Protocol):
    # {
    # 責務: [ai_score: 推論対象画像のAI生成スコアを取得する]
    # 処理: [1: 推論対象画像のAI生成スコアを取得する]
    # 引数: [self, path]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def ai_score(self, path: Path) -> float: ...


# {
# 責務: [ImageOriginResult: 画像単位の判定と証拠を保持する]
# フィールド: [状態: 画像単位の判定と証拠を保持する]
# }
@dataclass(frozen=True)
class ImageOriginResult:
    source_path: Path
    cluster: str
    confidence: float | None
    evidence: tuple[str, ...]
    reason: str
    user_override: bool = False


# {
# 責務: [discover_images: 入力root内の対応画像を列挙する]
# 処理: [1: 入力root内の対応画像を列挙する]
# 引数: [input_root, recursive, excluded_root]
# 戻り値: [宣言の戻り値を返す]
# }
def discover_images(
    input_root: Path, recursive: bool, excluded_root: Path | None = None
) -> list[Path]:
    root = input_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("入力元はフォルダーを指定してください")
    excluded = excluded_root.resolve() if excluded_root else None
    discovered: list[Path] = []
    if recursive:
        for current, directories, filenames in os.walk(
            root, followlinks=False, onerror=_raise_walk_error
        ):
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


# {
#   責務: [_raise_walk_error: 走査中に発生したディレクトリエラーを伝播する]
#   処理: [1: os.walkの走査エラーを呼び出し元へ返す]
#   引数: [error: 発生したファイルシステム例外]
#   戻り値: []
# }
def _raise_walk_error(error: OSError) -> None:
    raise error


# {
# 責務: [_is_within: pathが指定rootの配下か判定する]
# 処理: [1: pathが指定rootの配下か判定する]
# 引数: [path, parent]
# 戻り値: [宣言の戻り値を返す]
# }
def _is_within(path: Path, parent: Path | None) -> bool:
    if parent is None:
        return False
    try:
        path.resolve().relative_to(parent)
        return True
    except ValueError:
        return False


# {
# 責務: [_metadata_signal: metadataからAI生成区分を読み取る]
# 処理: [1: metadataからAI生成区分を読み取る]
# 引数: [metadata]
# 戻り値: [宣言の戻り値を返す]
# }
def _metadata_signal(metadata: object) -> str | None:
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


# {
# 責務: [_read_metadata: 画像とsidecarの判定根拠を読む]
# 処理: [1: 画像とsidecarの判定根拠を読む]
# 引数: [path]
# 戻り値: [宣言の戻り値を返す]
# }
def _read_metadata(path: Path) -> tuple[str | None, str | None]:
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
                key.casefold() in {"parameters", "workflow"} and embedded[key] for key in embedded
            ):
                signals.add(AI_LABEL)
                evidence.append("embedded_generation_metadata")
    except (OSError, ImportError):
        return "conflict", "image_metadata_read_error"

    if "conflict" in signals or len(signals) > 1:
        return "conflict", ",".join(evidence)
    return (next(iter(signals)), ",".join(evidence)) if signals else (None, None)


# {
# 責務: [classify_image: metadataと判定器から画像を分類する]
# 処理: [1: metadataと判定器から画像を分類する]
# 引数: [path, score_provider, low_threshold, high_threshold]
# 戻り値: [宣言の戻り値を返す]
# }
def classify_image(
    path: Path,
    score_provider: ScoreProvider,
    low_threshold: float,
    high_threshold: float,
) -> ImageOriginResult:
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
            None,
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


# {
# 責務: [classify_images: 画像一覧を分類して結果をまとめる]
# 処理: [1: 画像一覧を分類して結果をまとめる]
# 引数: [image_paths, score_provider, low_threshold, high_threshold, progress]
# 戻り値: [宣言の戻り値を返す]
# }
def classify_images(
    image_paths: Iterable[Path],
    score_provider: ScoreProvider,
    low_threshold: float = 0.1,
    high_threshold: float = 0.9,
    progress: Callable[[int, int, Path], None] | None = None,
) -> list[ImageOriginResult]:
    if not 0 <= low_threshold < high_threshold <= 1:
        raise ValueError("しきい値は 0 <= low < high <= 1 にしてください")
    paths = list(image_paths)
    results: list[ImageOriginResult] = []
    try:
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
    finally:
        close = getattr(score_provider, "close", None)
        if callable(close):
            close()
    return results


# {
# 責務: [copy_clusters: 画像とsidecarを分類先へ安全にコピーする]
# 処理: [1: 画像とsidecarを分類先へ安全にコピーする]
# 引数: [results, input_root, output_root]
# 戻り値: [宣言の戻り値を返す]
# }
def copy_clusters(results: Iterable[ImageOriginResult], input_root: Path, output_root: Path) -> int:
    source_root = input_root.resolve(strict=True)
    destination_root = output_root.resolve()
    if _is_within(destination_root, source_root) or destination_root == source_root:
        raise ValueError("出力先は入力フォルダーの外に指定してください")
    copied = 0
    created_files: list[Path] = []
    try:
        for result in results:
            if result.cluster not in CLUSTER_LABELS:
                raise ValueError(f"不明なクラスタです: {result.cluster}")
            if result.source_path.is_symlink():
                raise ValueError(f"シンボリックリンクはコピーできません: {result.source_path}")
            resolved_source = result.source_path.resolve(strict=True)
            try:
                relative_path = resolved_source.relative_to(source_root)
            except ValueError as error:
                raise ValueError(f"入力フォルダー外の画像です: {result.source_path}") from error
            destination = destination_root / result.cluster / relative_path
            _ensure_output_directory(destination_root, destination.parent)
            sidecars = [
                result.source_path.with_suffix(extension).resolve(strict=True)
                for extension in (".txt", ".json")
                if result.source_path.with_suffix(extension).is_file()
                and not result.source_path.with_suffix(extension).is_symlink()
            ]
            for sidecar in sidecars:
                try:
                    sidecar.relative_to(source_root)
                except ValueError as error:
                    raise ValueError(f"入力フォルダー外のsidecarです: {sidecar}") from error
            final_path = _destination_for_source(resolved_source, destination, sidecars)
            related_files = [
                (resolved_source, final_path),
                *[(sidecar, final_path.with_suffix(sidecar.suffix)) for sidecar in sidecars],
            ]
            for source_file, final_file in related_files:
                if _same_file_content(source_file, final_file):
                    continue
                _copy_file_atomically(source_file, final_file, source_root)
                created_files.append(final_file)
                if source_file == result.source_path:
                    copied += 1
    except BaseException:
        for created_file in reversed(created_files):
            created_file.unlink(missing_ok=True)
        raise
    return copied


# {
#   責務: [_ensure_output_directory: 出力先の親ディレクトリをroot内に安全に作成する]
#   処理: [1: 出力先の各階層にsymlinkがないことを確認して作成する]
#   引数: [output_root: 出力root, target_parent: ファイルの親ディレクトリ]
#   戻り値: []
# }
def _ensure_output_directory(output_root: Path, target_parent: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root.is_symlink():
        raise ValueError(f"出力rootにシンボリックリンクは使えません: {output_root}")
    root = output_root.resolve(strict=True)
    try:
        relative_parent = target_parent.relative_to(output_root)
    except ValueError as error:
        raise ValueError(f"出力先が出力rootの外です: {target_parent}") from error

    current = root
    for part in relative_parent.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"出力先の親にシンボリックリンクは使えません: {current}")
        current.mkdir(exist_ok=True)
        if current.is_symlink() or not _is_within(current.resolve(strict=True), root):
            raise ValueError(f"出力先の親が出力root外を指しています: {current}")


# {
#   責務: [_destination_for_source: 同一内容の既存出力を再利用する]
#   処理: [1: 希望パスと衝突候補を確認する, 2: 既存内容または未使用パスを返す]
#   引数: [source: コピー元, destination: 希望する出力パス]
#   戻り値: [未上書きで使用できる出力パス]
# }
def _destination_for_source(
    source: Path, destination: Path, companion_sources: Iterable[Path] = ()
) -> Path:
    companions_by_extension = {
        companion.suffix.casefold(): companion for companion in companion_sources
    }
    digest = hashlib.sha256(str(destination).encode("utf-8")).hexdigest()[:10]
    suffix_index = 0
    while True:
        if suffix_index == 0:
            suffix = ""
        elif suffix_index == 1:
            suffix = f"_{digest}"
        else:
            suffix = f"_{digest}_{suffix_index - 1}"
        candidate = destination.with_name(f"{destination.stem}{suffix}{destination.suffix}")
        if candidate.exists() and not _same_file_content(source, candidate):
            suffix_index += 1
            continue
        if _has_conflicting_sidecars(candidate, companions_by_extension):
            suffix_index += 1
            continue
        return candidate


# {
#   責務: [_has_conflicting_sidecars: 既存sidecarと出力候補が衝突するか判定する]
#   処理: [1: source側にないsidecarと内容が異なるsidecarを検出する]
#   引数: [candidate: 画像候補, companions_by_extension: source側sidecar一覧]
#   戻り値: [sidecar衝突があればTrue]
# }
def _has_conflicting_sidecars(candidate: Path, companions_by_extension: dict[str, Path]) -> bool:
    for extension in (".txt", ".json"):
        target = candidate.with_suffix(extension)
        if target == candidate:
            continue
        source = companions_by_extension.get(extension)
        if not target.exists():
            continue
        if source is None or not _same_file_content(source, target):
            return True
    return False


# {
#   責務: [_same_file_content: 2ファイルの内容が一致するか判定する]
#   処理: [1: SHA-256を読み比べる]
#   引数: [left: 先頭ファイル, right: 比較ファイル]
#   戻り値: [内容一致ならTrue]
# }
def _same_file_content(left: Path, right: Path) -> bool:
    if right.is_symlink() or not right.is_file():
        return False
    left_digest = _file_digest(left)
    right_digest = _file_digest(right)
    return left_digest == right_digest


# {
#   責務: [_file_digest: ファイルを小分けに読んでSHA-256を計算する]
#   処理: [1: 1 MiB単位で読みchecksumへ加える]
#   引数: [path: checksum対象]
#   戻り値: [SHA-256 digest bytes]
# }
def _file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


# {
# 責務: [_copy_file_atomically: 入力rootを検証して一時ファイル経由でコピーする]
# 処理: [1: sourceを開いて実体とroot内の位置を検証する, 2: 開いたdescriptorから公開する]
# 引数: [source: コピー元, destination: コピー先, allowed_root: コピーを許可するroot]
# 戻り値: [宣言の戻り値を返す]
# }
def _copy_file_atomically(
    source: Path, destination: Path, allowed_root: Path | None = None
) -> None:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.",
        suffix=".copying",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        with source.open("rb") as source_handle:
            opened_stat = os.fstat(source_handle.fileno())
            path_stat = source.lstat()
            if stat.S_ISLNK(path_stat.st_mode) or (
                opened_stat.st_dev,
                opened_stat.st_ino,
            ) != (path_stat.st_dev, path_stat.st_ino):
                raise ValueError(f"コピー中に入力ファイルが差し替えられました: {source}")
            resolved_source = source.resolve(strict=True)
            if allowed_root is not None and not _is_within(resolved_source, allowed_root):
                raise ValueError(f"入力root外のファイルはコピーできません: {source}")
            with temporary.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
            os.chmod(temporary, stat.S_IMODE(opened_stat.st_mode))
            os.utime(
                temporary,
                ns=(opened_stat.st_atime_ns, opened_stat.st_mtime_ns),
            )
            if opened_stat.st_size != temporary.stat().st_size:
                raise OSError(f"コピー検証に失敗しました: {source}")
        try:
            os.link(temporary, destination)
        except OSError as error:
            if not _hard_links_unsupported(error):
                raise
            created_destination = False
            try:
                with temporary.open("rb") as source_handle, destination.open("xb") as target_handle:
                    created_destination = True
                    shutil.copyfileobj(source_handle, target_handle)
                shutil.copystat(temporary, destination)
            except OSError:
                if created_destination:
                    destination.unlink(missing_ok=True)
                raise
    finally:
        temporary.unlink(missing_ok=True)


# {
#   責務: [_hard_links_unsupported: hard link非対応filesystemの例外を識別する]
#   処理: [1: errnoとWindows error codeを確認する]
#   引数: [error: hard link作成エラー]
#   戻り値: [代替コピー可能ならTrue]
# }
def _hard_links_unsupported(error: OSError) -> bool:
    unsupported_errnos = {
        errno.EPERM,
        errno.EXDEV,
        errno.ENOTSUP,
        errno.EOPNOTSUPP,
        errno.ENOSYS,
    }
    return error.errno in unsupported_errnos or getattr(error, "winerror", None) in {
        1,
        17,
        50,
    }


# {
# 責務: [write_manifest: 判定結果をJSON manifestへ保存する]
# 処理: [1: 判定結果をJSON manifestへ保存する]
# 引数: [results, manifest_path]
# 戻り値: [宣言の戻り値を返す]
# }
def write_manifest(results: Iterable[ImageOriginResult], manifest_path: Path) -> Path:
    with _MANIFEST_LOCK:
        return _write_manifest_locked(results, manifest_path)


# {
#   責務: [_write_manifest_locked: manifestを衝突回避して保存する]
#   処理: [1: 内容を一時ファイルに書く, 2: 同一内容を再利用または排他的に公開する]
#   引数: [results: 判定結果, manifest_path: 保存先]
#   戻り値: [保存したmanifestパス]
# }
def _write_manifest_locked(results: Iterable[ImageOriginResult], manifest_path: Path) -> Path:
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
    serialized = json.dumps(rows, ensure_ascii=False, indent=2)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
        dir=manifest_path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        final_path = _destination_for_source(temporary, manifest_path)
        if _same_file_content(temporary, final_path):
            return final_path
        _copy_file_atomically(temporary, final_path)
    finally:
        temporary.unlink(missing_ok=True)
    return final_path
