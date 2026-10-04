import json

import tkinter as tk

from ..context import USER_INPUT_DIR


# {
#   "責務": "backendごと、tab classごとのTk variable値を起動間で保存・復元する。",
#   "フィールド": ["backend: 設定namespace", "path: last_settings.json location"]
# }
class LastSettingsStore:
    """タブに表示される Tk 変数を、次回起動用に保存する。"""

    # {
    #   "責務": "backend namespaceと最終設定JSON pathを初期化する。",
    #   "処理": ["backendを保持する", "common user config下のJSON pathを決める"],
    #   "引数": {"backend": "backend識別子"}, "戻り値": []
    # }
    def __init__(self, backend):
        self.backend = backend
        self.path = USER_INPUT_DIR / "config" / "common" / "last_settings.json"

    # {
    #   "責務": "tab classに保存されたTk variable値を復元する。",
    #   "処理": ["backend/tab別dictを読む", "対応属性がTk Variableの場合のみsetし不正値を無視する"],
    #   "引数": {"tab": "復元対象tab instance"}, "戻り値": []
    # }
    def restore(self, tab):
        values = self._load().get(self.backend, {}).get(type(tab).__name__, {})
        if not isinstance(values, dict):
            return
        for name, value in values.items():
            variable = getattr(tab, name, None)
            if isinstance(variable, tk.Variable):
                try:
                    variable.set(value)
                except (tk.TclError, TypeError, ValueError):
                    continue

    # {
    #   "責務": "tab群のTk variable値をbackend別JSONへ保存する。",
    #   "処理": ["既存JSONを読みbackend/tab値を更新する", "parent directoryを作成してUTF-8 JSONを書き込む"],
    #   "引数": {"tabs": "保存対象tab instance iterable"}, "戻り値": []
    # }
    def save(self, tabs):
        data = self._load()
        backend_values = data.setdefault(self.backend, {})
        for tab in tabs:
            backend_values[type(tab).__name__] = self._variables(tab)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # {
    #   "責務": "最終設定JSONを読みdict形式だけ返す。",
    #   "処理": ["JSONを読みI/O・parse errorなら空dictへfallbackする"],
    #   "引数": [], "戻り値": "config dict"
    # }
    def _load(self):
        try:
            with self.path.open(encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    # {
    #   "責務": "tab instance内のTk Variable値をJSON保存可能なdictへ抽出する。",
    #   "処理": ["varsを走査しTk Variableのみgetする", "TclErrorが起きる変数を除外する"],
    #   "引数": {"tab": "値を収集するtab instance"}, "戻り値": "属性名/value dict"
    # }
    @staticmethod
    def _variables(tab):
        values = {}
        for name, value in vars(tab).items():
            if not isinstance(value, tk.Variable):
                continue
            try:
                values[name] = value.get()
            except tk.TclError:
                continue
        return values
