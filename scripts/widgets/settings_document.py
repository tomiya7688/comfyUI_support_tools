"""Versioned persistence format for GUI settings, independent of Tk widgets."""

import json
from pathlib import Path

CURRENT_SCHEMA_VERSION = 1


# {
#   責務: [empty_settings_document: 初期設定保存用の空schema文書を作る]
#   処理: [現在のschema versionと空のbackend領域を含むdictを返す]
#   引数: []
#   戻り値: [dict: versioned settings document]
# }
def empty_settings_document():
    return {"schema_version": CURRENT_SCHEMA_VERSION, "backends": {}}


# {
#   責務: [load_settings_document: legacyまたはversioned JSONを現在のsettings schemaへ読み替える]
#   処理: [JSONを読み, legacy backend mapをschema version 1へ移行し, 不正JSONやencodingなら空文書を返し, 未対応schemaを拒否する]
#   引数: [path: 設定JSONのPath]
#   戻り値: [dict: 現在のschema versionを持つsettings document]
#   エラー: [OSError: schema versionまたはversioned document structureが未対応の場合]
# }
def load_settings_document(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_settings_document()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty_settings_document()

    if not isinstance(payload, dict):
        return empty_settings_document()

    if "schema_version" not in payload:
        return {"schema_version": CURRENT_SCHEMA_VERSION, "backends": payload}

    version = payload.get("schema_version")
    if version != CURRENT_SCHEMA_VERSION:
        raise OSError(f"未対応の設定schema versionです: {version}")
    backends = payload.get("backends")
    if not isinstance(backends, dict):
        raise OSError("設定schemaのbackendsはobjectである必要があります")
    return {"schema_version": CURRENT_SCHEMA_VERSION, "backends": backends}


# {
#   責務: [save_settings_document: 現在のsettings schemaをJSONとして保存する]
#   処理: [親folderを作成し, schema versionを正規化してUTF-8 JSONを書き込む]
#   引数: [path: 保存先Path, document: 保存するsettings document]
#   戻り値: []
#   エラー: [OSError: 保存先への書き込みに失敗した場合, ValueError: backendsがobjectでない場合]
# }
def save_settings_document(path: Path, document: dict) -> None:
    backends = document.get("backends")
    if not isinstance(backends, dict):
        raise ValueError("設定schemaのbackendsはobjectである必要があります")
    current = {"schema_version": CURRENT_SCHEMA_VERSION, "backends": backends}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
