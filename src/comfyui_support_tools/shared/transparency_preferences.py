"""Small, secret-free persistent defaults for transparency preferences."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


# {
# 責務: [ TransparencyPreferenceStore: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class TransparencyPreferenceStore:
    """Persist global and per-application enablement; defaults to OFF."""

    # {
    # 責務: [ __init__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, path]
    # 戻り値: [処理結果]
    # }
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else self.default_path()

    # {
    # 責務: [ default_path: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [なし]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def default_path() -> Path:
        if os.name == "nt":
            root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return root / "comfyui_support_tools" / "transparency.json"

    # {
    # 責務: [ _read: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def _read(self) -> dict[str, Any]:
        if self.path.is_symlink():
            raise ValueError("transparency preference file must not be a symbolic link")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema_version": 1, "global_enabled": False, "application_overrides": {}}
        except json.JSONDecodeError as exc:
            raise ValueError("transparency preference file is not valid JSON") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or not isinstance(payload.get("global_enabled"), bool)
            or not isinstance(payload.get("application_overrides"), dict)
            or any(
                not isinstance(key, str) or not isinstance(value, bool)
                for key, value in payload["application_overrides"].items()
            )
        ):
            raise ValueError("transparency preference schema is invalid")
        return payload

    # {
    # 責務: [ global_enabled: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def global_enabled(self) -> bool:
        return self._read()["global_enabled"]

    # {
    # 責務: [ application_override: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, application_id]
    # 戻り値: [処理結果]
    # }
    def application_override(self, application_id: str) -> bool | None:
        return self._read()["application_overrides"].get(application_id)

    # {
    # 責務: [ set_global_enabled: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, enabled]
    # 戻り値: [処理結果]
    # }
    def set_global_enabled(self, enabled: bool) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("global transparency preference must be boolean")
        payload = self._read()
        payload["global_enabled"] = enabled
        self._write(payload)

    # {
    # 責務: [ set_application_override: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, application_id, enabled]
    # 戻り値: [処理結果]
    # }
    def set_application_override(self, application_id: str, enabled: bool | None) -> None:
        if not application_id.strip() or (enabled is not None and not isinstance(enabled, bool)):
            raise ValueError("application override requires an id and boolean or None")
        payload = self._read()
        if enabled is None:
            payload["application_overrides"].pop(application_id, None)
        else:
            payload["application_overrides"][application_id] = enabled
        self._write(payload)

    # {
    # 責務: [ _write: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, payload]
    # 戻り値: [処理結果]
    # }
    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("transparency preference file must not be a symbolic link")
        encoded = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
