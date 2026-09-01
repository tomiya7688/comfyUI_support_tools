import json

import tkinter as tk

from ..context import USER_INPUT_DIR


class LastSettingsStore:
    """タブに表示される Tk 変数を、次回起動用に保存する。"""

    def __init__(self, backend):
        self.backend = backend
        self.path = USER_INPUT_DIR / "config" / "common" / "last_settings.json"

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

    def save(self, tabs):
        data = self._load()
        backend_values = data.setdefault(self.backend, {})
        for tab in tabs:
            backend_values[type(tab).__name__] = self._variables(tab)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load(self):
        try:
            with self.path.open(encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

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
