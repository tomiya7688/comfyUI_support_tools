import json
import re
from pathlib import Path

from ..context import USER_INPUT_DIR


# {
#   責務: [PresetStore: tab-specific preset JSON storageを管理する]
#   処理: [derive preset directory and provide names, save, and load operations]
#   フィールド: [directory]
# }
class PresetStore:
    """タブ別プリセットJSONの保存と読み込みを担当する。"""

    # {
    #   責務: [__init__: tab名からpreset directory pathを初期化する]
    #   処理: [store path under user input preset area without filesystem writes]
    #   引数: [tab_name]
    #   戻り値: [処理結果]
    # }
    def __init__(self, tab_name):
        self.directory = USER_INPUT_DIR / "preset" / tab_name

    # {
    #   責務: [names: preset directory内のJSON stem namesをsorted listで返す]
    #   処理: [return empty when directory is absent or list files case-insensitively]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def names(self):
        if not self.directory.is_dir():
            return []
        return [
            path.stem
            for path in sorted(self.directory.glob("*.json"), key=lambda path: path.name.casefold())
        ]

    # {
    #   責務: [save: validated preset name and valuesをJSON fileへ保存する]
    #   処理: [sanitize invalid filename characters, create directory, write UTF-8 JSON, and return path]
    #   引数: [name, values]
    #   戻り値: [処理結果]
    # }
    def save(self, name, values):
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", name.strip())
        if not safe_name:
            raise ValueError("プリセット名を入力してください")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{safe_name}.json"
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    # {
    #   責務: [load: named JSON presetを読み込みmappingを返す]
    #   処理: [read file and reject non-object JSON values]
    #   引数: [name]
    #   戻り値: [処理結果]
    # }
    def load(self, name):
        path = self.directory / f"{name}.json"
        with path.open(encoding="utf-8") as source:
            values = json.load(source)
        if not isinstance(values, dict):
            raise ValueError("プリセットの形式が不正です")
        return values
