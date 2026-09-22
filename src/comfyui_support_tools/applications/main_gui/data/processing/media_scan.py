"""Read-only, cancellable directory traversal. No decoder runs during scanning."""
import hashlib
import os
from pathlib import Path
from threading import Event
from collections.abc import Callable

from comfyui_support_tools.shared.contracts.media_event import MediaEvent
from comfyui_support_tools.shared.contracts.media_item import MediaItem

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
COLLECTIONS = {"library", "dataset", "generated"}
MAX_ITEMS = 100_000
BATCH_SIZE = 128


def scan_folder(folder: str, collection: str, token: int, cancel: Event,
                emit: Callable[[MediaEvent], None]) -> None:
    """Emit up to MAX_ITEMS records; never follow directory/file symlinks."""
    batch = []
    count = 0
    failures = 0
    limited = False
    try:
        if collection not in COLLECTIONS or not folder.strip():
            raise ValueError("フォルダと分類を指定してください")
        root = Path(folder).expanduser().absolute()
        if not root.is_dir():
            raise ValueError("フォルダが見つかりません: " + str(root))
        pending = [str(root)]
        while pending and not cancel.is_set() and not limited:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if cancel.is_set():
                            return
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(entry.path)
                                continue
                            suffix = Path(entry.name).suffix.lower()
                            kind = "image" if suffix in IMAGE_SUFFIXES else "video" if suffix in VIDEO_SUFFIXES else ""
                            if not kind or not entry.is_file(follow_symlinks=False):
                                continue
                            stat = entry.stat(follow_symlinks=False)
                            path = os.path.abspath(entry.path)
                            identity = hashlib.sha256(os.path.normcase(path).encode("utf-8", "surrogatepass")).hexdigest()
                            batch.append(MediaItem(identity, path, entry.name, kind, collection,
                                                   stat.st_size, stat.st_mtime_ns))
                            count += 1
                            if len(batch) >= BATCH_SIZE:
                                emit(MediaEvent("batch", token, tuple(batch)))
                                batch.clear()
                            if count >= MAX_ITEMS:
                                limited = True
                                break
                        except OSError:
                            failures += 1
            except OSError:
                failures += 1
        if cancel.is_set():
            return
        if batch:
            emit(MediaEvent("batch", token, tuple(batch)))
        message = f"読込完了: {count} 件"
        if failures:
            message += f" / 読み取れない項目: {failures} 件"
        if limited:
            message += f" / 上限 {MAX_ITEMS:,} 件。小さいフォルダで開き直してください"
        emit(MediaEvent("done", token, message=message))
    except (OSError, ValueError) as exc:
        emit(MediaEvent("error", token, message=str(exc)))
