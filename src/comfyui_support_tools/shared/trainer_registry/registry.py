"""Resolve current trainer capabilities and safe automatic method choices."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from .adapters import RuntimeTrainerAdapter
from .contracts import (
    AdapterMethod,
    ArchitectureProfile,
    MethodSupport,
    SupportLevel,
    SupportMatrixEntry,
    TrainerResolution,
)


# {
# 責務: [TrainerSupportRegistry: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class TrainerSupportRegistry:
    """Resolve a trainer only after versioned runtime support is confirmed."""

    # {
    # 責務: [__init__: register trainers, profiles, priority and capability cache]
    # 処理: [keep the registry independent from any one trainer implementation]
    # 引数: [adapters: runtime trainer adapters, profiles: architecture map, cache_path: optional JSON support cache, priority: automatic trainer order]
    # 戻り値: [None: registry ready]
    # }
    def __init__(
        self,
        adapters: Sequence[RuntimeTrainerAdapter],
        profiles: Mapping[str, ArchitectureProfile],
        cache_path: str | Path | None = None,
        priority: Sequence[str] = ("simpletuner", "ai_toolkit", "sd_scripts"),
    ) -> None:
        names = [adapter.trainer_name for adapter in adapters]
        if len(set(names)) != len(names):
            raise ValueError("trainer adapter names must be unique")
        self.adapters = {adapter.trainer_name: adapter for adapter in adapters}
        self.profiles = dict(profiles)
        self.cache_path = Path(cache_path).expanduser() if cache_path else None
        self.priority = tuple(priority)
        self._matrix_cache: dict[tuple[str, str], SupportMatrixEntry] = {}

    # {
    # 責務: [support_matrix: inspect each trainer's current profile capabilities]
    # 処理: [probe version and manifest fingerprint, then expose method/precision/quantization/module support]
    # 引数: [architecture: profile key, refresh: force a new runtime probe]
    # 戻り値: [tuple[SupportMatrixEntry, ...]: runtime capability matrix rows]
    # }
    def support_matrix(
        self, architecture: str, refresh: bool = False
    ) -> tuple[SupportMatrixEntry, ...]:
        if architecture not in self.profiles:
            raise ValueError(f"unknown architecture profile: {architecture}")
        cached = {} if refresh else self._read_cache()
        if refresh:
            self._matrix_cache = {
                key: value for key, value in self._matrix_cache.items() if key[0] != architecture
            }
        profile = self.profiles[architecture]
        rows = []
        for name, adapter in self.adapters.items():
            probe = adapter.probe()
            for key, value in tuple(cached.items()):
                if (
                    isinstance(value, dict)
                    and value.get("trainer") == name
                    and value.get("architecture") == architecture
                ):
                    del cached[key]
            cache_key = cache_fingerprint(
                name, probe.version, architecture, probe.capability_fingerprint
            )
            cached[cache_key] = {
                "trainer": name,
                "architecture": architecture,
                "version": probe.version,
                "fingerprint": probe.capability_fingerprint,
            }
            cache_identity = (architecture, probe.capability_fingerprint)
            row = self._matrix_cache.get(cache_identity)
            if row is None:
                methods = adapter.supported_methods(architecture)
                row = SupportMatrixEntry(
                    trainer=name,
                    architecture=architecture,
                    version=probe.version,
                    methods=methods,
                    precision=adapter.supported_precision(architecture),
                    quantization=adapter.supported_quantization(architecture),
                    features=adapter.supported_features(architecture),
                    target_modules=adapter.target_modules(architecture),
                    minimum_vram_gib=profile.minimum_vram_gib,
                    capability_fingerprint=probe.capability_fingerprint,
                )
                self._matrix_cache[cache_identity] = row
            rows.append(row)
        self._write_cache(cached)
        return tuple(rows)

    # {
    # 責務: [resolve: select only supported Auto choices or a valid manual trainer]
    # 処理: [probe current capabilities, permit experimental only when pinned, and reject unsupported requests]
    # 引数: [architecture: profile key, method: requested adapter method, trainer: Auto or explicit trainer]
    # 戻り値: [TrainerResolution: selected adapter or explicit unsupported result]
    # }
    def resolve(
        self,
        architecture: str,
        method: AdapterMethod,
        trainer: str = "auto",
    ) -> TrainerResolution:
        matrix = {row.trainer: row for row in self.support_matrix(architecture)}
        if trainer.casefold() != "auto":
            trainer_name = next(
                (name for name in self.adapters if name.casefold() == trainer.casefold()), None
            )
            selected = self.adapters.get(trainer_name) if trainer_name else None
            if selected is None:
                return TrainerResolution(
                    None,
                    method,
                    architecture,
                    SupportLevel.UNSUPPORTED,
                    f"Unknown trainer: {trainer}",
                )
            trainer = selected.trainer_name
            row = matrix[trainer]
            level = self._method_level(row, method)
            if level is SupportLevel.UNSUPPORTED:
                return TrainerResolution(
                    None,
                    method,
                    architecture,
                    level,
                    f"{trainer} does not support {method.value} for {architecture}",
                )
            return TrainerResolution(
                trainer,
                method,
                architecture,
                level,
                "manually pinned trainer passed the runtime capability check",
            )
        for name in self.priority:
            row = matrix.get(name)
            if row is not None and self._method_level(row, method) is SupportLevel.SUPPORTED:
                return TrainerResolution(
                    name,
                    method,
                    architecture,
                    SupportLevel.SUPPORTED,
                    "first runtime-supported Auto candidate",
                )
        return TrainerResolution(
            None,
            method,
            architecture,
            SupportLevel.UNSUPPORTED,
            "no runtime-supported Auto trainer is available",
        )

    # {
    # 責務: [_method_level: find one method's resolved support state]
    # 処理: [return unsupported when no matching capability declaration exists]
    # 引数: [row: support matrix entry, method: adapter method]
    # 戻り値: [SupportLevel: resolved level]
    # }
    @staticmethod
    def _method_level(row: SupportMatrixEntry, method: AdapterMethod) -> SupportLevel:
        return next(
            (item.level for item in row.methods if item.method is method),
            SupportLevel.UNSUPPORTED,
        )

    # {
    # 責務: [_read_cache: load bounded support fingerprint cache]
    # 処理: [ignore malformed stale cache and reject symlinks or oversized files]
    # 引数: [self: registry]
    # 戻り値: [dict[str, object]: current cache entries]
    # }
    def _read_cache(self) -> dict[str, object]:
        if self.cache_path is None or not self.cache_path.exists():
            return {}
        if self.cache_path.is_symlink() or self.cache_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("trainer support cache must be a bounded regular file")
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    # {
    # 責務: [_write_cache: atomically replace trainer support cache]
    # 処理: [bound entry count and write through a same-directory temporary file]
    # 引数: [self: registry, payload: current fingerprint entries]
    # 戻り値: [None: cache persisted]
    # }
    def _write_cache(self, payload: dict[str, object]) -> None:
        if self.cache_path is None:
            return
        path = self.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("trainer support cache cannot be a symlink")
        encoded = json.dumps(dict(list(payload.items())[-500:]), sort_keys=True, indent=2).encode()
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    # {
    # 責務: [invalidate_cache: remove support data after manual trainer update]
    # 処理: [delete only the registry-owned cache document]
    # 引数: [self: registry]
    # 戻り値: [None: future query reprobes all trainer versions]
    # }
    def invalidate_cache(self) -> None:
        self._matrix_cache.clear()
        if self.cache_path is None:
            return
        if self.cache_path.is_symlink():
            raise ValueError("trainer support cache cannot be a symlink")
        self.cache_path.unlink(missing_ok=True)


# {
# 責務: [cache_fingerprint: create a stable public matrix cache identity]
# 処理: [hash trainer name, runtime version, profile and capability fingerprint]
# 引数: [trainer: normalized trainer name, version: installed version, architecture: profile, capability_fingerprint: manifest/version hash]
# 戻り値: [str: SHA-256 cache identity]
# }
def cache_fingerprint(
    trainer: str, version: str | None, architecture: str, capability_fingerprint: str
) -> str:
    material = "\0".join((trainer, version or "", architecture, capability_fingerprint))
    return hashlib.sha256(material.encode()).hexdigest()
