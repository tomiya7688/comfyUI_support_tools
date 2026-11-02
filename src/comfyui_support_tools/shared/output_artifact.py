from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# {
# 責務: [ConflictPolicy: 出力collision時の明示的動作を定義する]
# フィールド: [FAIL/SKIP/OVERWRITE/RENAME/VERSIONED]
# 処理: []
# }
class ConflictPolicy(str, Enum):
    FAIL = "fail"
    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"
    VERSIONED = "versioned"


# {
# 責務: [ArtifactState: output artifactのlifecycle状態を定義する]
# フィールド: [PLANNED/WRITING/COMPLETE/FAILED/QUARANTINED/SUPERSEDED]
# 処理: []
# }
class ArtifactState(str, Enum):
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETE = "complete"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"


# {
# 責務: [ ArtifactRef: source/outputとartifact lifecycle状態を表現する ]
# フィールド: [ source: 入力path, target: 出力path, state: lifecycle, group_id: sidecar group ]
# 処理: []
# }
@dataclass(frozen=True)
class ArtifactRef:
    source: Path | None
    target: Path
    state: ArtifactState = ArtifactState.PLANNED
    group_id: str | None = None
    error: str | None = None


# {
# 責務: [ safe_filename: UnicodeとOS予約文字を安全なstemへ正規化する ]
# 処理: [ 1: Unicodeをnormalizeする, 2: 制御/予約文字を置換する, 3: Windows reserved nameを回避する ]
# 引数: [ value: 入力stem ]
# 戻り値: [ filename: 安全化stem ]
# }
def safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", normalized).strip(" .")
    if not cleaned:
        cleaned = "artifact"
    if cleaned.split(".", 1)[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        cleaned = f"_{cleaned}"
    return cleaned


# {
# 責務: [ resolve_conflict: target collision policyに従い書き先を選ぶ ]
# 処理: [ 1: source collisionを拒否する, 2: policyに応じてskip/overwrite/rename/versionする ]
# 引数: [ target: requested path, policy: collision policy, source_paths: 入力path群 ]
# 戻り値: [ path: resolved pathまたはNone(skip) ]
# }
def resolve_conflict(
    target: Path,
    policy: ConflictPolicy,
    source_paths: Iterable[Path] = (),
) -> Path | None:
    absolute = target.expanduser().absolute()
    sources = {item.expanduser().absolute() for item in source_paths}
    if absolute in sources:
        raise ValueError(f"Output path collides with an input source: {absolute}")
    if not absolute.exists() and not absolute.is_symlink():
        return absolute
    if policy is ConflictPolicy.FAIL:
        raise FileExistsError(absolute)
    if policy is ConflictPolicy.SKIP:
        return None
    if policy is ConflictPolicy.OVERWRITE:
        return absolute
    index = 1
    while True:
        suffix = f".v{index:03d}" if policy is ConflictPolicy.VERSIONED else f" ({index})"
        candidate = absolute.with_name(f"{absolute.stem}{suffix}{absolute.suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        index += 1


# {
# 責務: [ atomic_write_bytes: validate後に同一directoryからatomic commitする ]
# 処理: [ 1: safe targetを選ぶ, 2: sibling tempへwrite/fsyncする, 3: validateしてatomic commitする, 4: failure tempをcleanupする ]
# 引数: [ target: 出力path, content: bytes, policy: conflict policy, validator: staged file validator, source_paths: 入力path群 ]
# 戻り値: [ artifact: 最終ArtifactRef、skip時はNone ]
# }
def atomic_write_bytes(
    target: Path,
    content: bytes,
    *,
    source: Path | None = None,
    policy: ConflictPolicy = ConflictPolicy.FAIL,
    validator: Callable[[Path], None] | None = None,
    source_paths: Iterable[Path] = (),
    group_id: str | None = None,
) -> ArtifactRef | None:
    sources = tuple(source_paths) + ((source,) if source is not None else ())
    destination = resolve_conflict(target, policy, sources)
    if destination is None:
        return None
    if destination.is_symlink():
        raise ValueError(f"Symbolic-link output is not allowed: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {destination.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if validator is not None:
            validator(temporary)
        if policy in {ConflictPolicy.RENAME, ConflictPolicy.VERSIONED}:
            try:
                os.link(temporary, destination)
            except FileExistsError:
                return atomic_write_bytes(
                    target,
                    content,
                    policy=policy,
                    validator=validator,
                    source_paths=sources,
                    source=source,
                    group_id=group_id,
                )
            temporary.unlink()
        elif policy is ConflictPolicy.OVERWRITE:
            os.replace(temporary, destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if policy is ConflictPolicy.SKIP:
                    temporary.unlink(missing_ok=True)
                    return None
                raise FileExistsError(destination) from None
            temporary.unlink()
        return ArtifactRef(source, destination, ArtifactState.COMPLETE, group_id)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
