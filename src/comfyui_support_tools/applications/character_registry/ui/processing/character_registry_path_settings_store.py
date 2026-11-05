from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


# {
#   責務: [CharacterRegistryPathSettingsStore: UIのdataset/profile pathを明示されたuser_data JSONへ保存する]
#   フィールド: [_settings_path: 呼び出し元が構成したuser_data JSON path]
# }
class CharacterRegistryPathSettingsStore:
    # {
    #   責務: [__init__: 明示設定pathをsettings storeへ保持する]
    #   処理: [str/PathをPathへ変換してinstance stateへ設定する]
    #   引数: [self: settings store, settings_path: user_data JSON file]
    #   戻り値: []
    # }
    def __init__(self, settings_path: str | Path) -> None:
        self._settings_path = Path(settings_path)

    # {
    #   責務: [load: 保存済みdataset/profile pathを読み込む]
    #   処理: [JSON objectを検証し, 未設定keyは空文字にする]
    #   引数: [self: settings store]
    #   戻り値: [dict[str, str]: dataset_root/profile_directory設定]
    #   エラー: [ValueError: JSON形式またはfield型が不正な場合]
    # }
    def load(self) -> dict[str, str]:
        try:
            value: Any = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            value = {}
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Character Registry path設定を読めません: {error}") from error
        if not isinstance(value, dict):
            raise ValueError("Character Registry path設定はJSON objectである必要があります")
        dataset_root = value.get("dataset_root", "")
        profile_directory = value.get("profile_directory", "")
        if not isinstance(dataset_root, str) or not isinstance(profile_directory, str):
            raise ValueError("dataset_rootとprofile_directoryは文字列で指定してください")
        return {"dataset_root": dataset_root, "profile_directory": profile_directory}

    # {
    #   責務: [save: dataset/profile pathをatomicにuser_data JSONへ保存する]
    #   処理: [親directoryを作り, temporary fileからos.replaceで置換する]
    #   引数: [self: settings store, dataset_root: caption dataset root, profile_directory: profile storage root]
    #   戻り値: []
    #   エラー: [OSError: 設定fileを安全に保存できない場合, ValueError: 値が文字列でない場合]
    # }
    def save(self, dataset_root: str, profile_directory: str) -> None:
        if not isinstance(dataset_root, str) or not isinstance(profile_directory, str):
            raise ValueError("dataset_rootとprofile_directoryは文字列で指定してください")
        parent = self._settings_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"dataset_root": dataset_root, "profile_directory": profile_directory},
            ensure_ascii=False,
            indent=2,
        )
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._settings_path.stem}.", suffix=".tmp", dir=parent
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self._settings_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
