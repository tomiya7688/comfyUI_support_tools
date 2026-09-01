import json
import re
from pathlib import Path

from ..context import USER_INPUT_DIR


class PresetStore:
    """タブ別プリセットJSONの保存と読み込みを担当する。"""

    def __init__(self, tab_name):
        self.directory = USER_INPUT_DIR / "preset" / tab_name

    def names(self):
        if not self.directory.is_dir():
            return []
        return [path.stem for path in sorted(self.directory.glob("*.json"), key=lambda path: path.name.casefold())]

    def save(self, name, values):
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", name.strip())
        if not safe_name:
            raise ValueError("プリセット名を入力してください")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{safe_name}.json"
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, name):
        path = self.directory / f"{name}.json"
        with path.open(encoding="utf-8") as source:
            values = json.load(source)
        if not isinstance(values, dict):
            raise ValueError("プリセットの形式が不正です")
        return values
