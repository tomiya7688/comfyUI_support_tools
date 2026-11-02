"""Immutable image and JSON history storage for expression edits."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from comfyui_support_tools.applications.expression_retouch.data.processing.face_mask import (
    _decode_rgb,
)


# {
#   責務: [ExpressionRetouchStore: persist immutable sources, masks, candidates, and edit history]
#   フィールド: [no mutable state]
#   処理: [validate one workspace and atomically store uniquely named run artifacts]
# }
class ExpressionRetouchStore:
    # {
    #   責務: [save_run: save one retouch run and its reproducibility metadata]
    #   処理: [1: validate workspace, 2: save source/mask/candidates, 3: atomically write JSON manifest]
    #   引数: [workspace: user-selected absolute directory, source: original image bytes, mask: edit mask bytes, candidates: candidate rows, metadata: target/backend settings]
    #   戻り値: [tuple[str, tuple[str, ...], str, str]: source hash, candidate paths, mask path, manifest path]
    # }
    def save_run(
        self,
        workspace: str | Path,
        source: bytes,
        mask: bytes,
        candidates: tuple[tuple[bytes, dict[str, Any]], ...],
        metadata: dict[str, Any],
    ) -> tuple[str, tuple[str, ...], str, str]:
        root = Path(workspace).expanduser()
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("workspace must be an absolute directory, not a symbolic link")
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        source_image = _decode_rgb(source)
        source_hash = hashlib.sha256(source).hexdigest()
        run_id = uuid.uuid4().hex
        source_path = root / "sources" / f"{source_hash}.png"
        mask_path = root / "masks" / f"{run_id}.png"
        self._save_image_once(source_path, source_image)
        try:
            with Image.open(io.BytesIO(mask)) as mask_image:
                if mask_image.size != source_image.size:
                    raise ValueError("edit mask dimensions must match the source image")
                normalized_mask = mask_image.convert("L")
                normalized_mask.load()
        except OSError as error:
            raise ValueError("edit mask image is malformed") from error
        self._save_image_once(mask_path, normalized_mask)
        candidate_paths = []
        manifest_candidates = []
        for index, (image_bytes, candidate_metadata) in enumerate(candidates):
            relative = Path("candidates") / f"{run_id}-{index:02d}.png"
            self._save_image_once(root / relative, _decode_rgb(image_bytes))
            candidate_paths.append(relative.as_posix())
            manifest_candidates.append({"path": relative.as_posix(), **candidate_metadata})
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "source_sha256": source_hash,
            "source_path": source_path.relative_to(root).as_posix(),
            "mask_path": mask_path.relative_to(root).as_posix(),
            "metadata": metadata,
            "candidates": manifest_candidates,
        }
        manifest_path = root / "history" / f"{run_id}.json"
        self._atomic_write(
            manifest_path,
            (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
                "utf-8"
            ),
        )
        return (
            source_hash,
            tuple(candidate_paths),
            mask_path.relative_to(root).as_posix(),
            manifest_path.relative_to(root).as_posix(),
        )

    # {
    #   責務: [_save_image_once: encode and exclusively persist one immutable image]
    #   処理: [1: create the parent, 2: reserve path without overwrite, 3: encode PNG bytes]
    #   引数: [self: store, path: destination, image: validated raster]
    #   戻り値: []
    # }
    def _save_image_once(self, path: Path, image: Image.Image) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                image.save(stream, format="PNG", optimize=True)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    # {
    #   責務: [_atomic_write: atomically publish one JSON manifest]
    #   処理: [write/fsync a unique sibling temp file, then replace the destination]
    #   引数: [self: store, path: metadata destination, content: UTF-8 JSON bytes]
    #   戻り値: []
    # }
    def _atomic_write(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
