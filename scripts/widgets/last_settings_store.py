import tkinter as tk

from src.comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings

from ..context import USER_INPUT_DIR
from .settings_document import load_settings_document, save_settings_document

STABLE_SETTINGS_IDS = {"RandomImageTab": "generation.random_image"}


# {
#   責務: [LastSettingsStore: GUI tabの直近設定をversioned document経由で保存・復元する]
#   フィールド: [backend: 設定を分離するbackend key, path: 設定JSONの保存先]
#   処理: [Tk変数の読み書きとsettings documentの永続化を仲介する]
# }
class LastSettingsStore:
    """タブに表示される Tk 変数を、次回起動用に保存する。"""

    # {
    #   責務: [__init__: backend用settings storeを初期化する]
    #   処理: [backend識別子と既定settings JSON pathを保持する]
    #   引数: [self: store instance, backend: backend識別子]
    #   戻り値: []
    # }
    def __init__(self, backend):
        self.backend = backend
        self.path = USER_INPUT_DIR / "config" / "common" / "last_settings.json"

    # {
    #   責務: [restore: 保存済みtab設定をTk変数へ戻す]
    #   処理: [backendとtab keyに対応する値を読み, 未対応schemaなら復元を飛ばし, 利用可能なTk variableへ設定する]
    #   引数: [self: store instance, tab: 設定を復元するtab]
    #   戻り値: []
    # }
    def restore(self, tab):
        try:
            backend_values = self._load().get("backends", {}).get(self.backend, {})
        except OSError:
            return
        feature_id = self._feature_id(tab)
        values = backend_values.get(feature_id)
        if values is None and feature_id != type(tab).__name__:
            values = backend_values.get(type(tab).__name__, {})
        if values is None:
            values = {}
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
    #   責務: [save: 全tabの直近設定を現在のschemaで保存する]
    #   処理: [既存documentを保持し, 各tabのTk variable値を更新してJSONへ保存する]
    #   引数: [self: store instance, tabs: 設定対象tabのiterable]
    #   戻り値: []
    #   エラー: [OSError: 設定保存に失敗した場合または未対応schemaの場合]
    # }
    def save(self, tabs):
        data = self._load()
        backend_values = data["backends"].setdefault(self.backend, {})
        for tab in tabs:
            settings = self._variables(tab)
            backend_values[settings.feature_id] = dict(settings.values)
            legacy_key = type(tab).__name__
            if settings.feature_id != legacy_key:
                backend_values.pop(legacy_key, None)
        save_settings_document(self.path, data)

    # {
    #   責務: [_load: 設定JSONを現在のversioned documentとして取得する]
    #   処理: [settings document moduleへloadとlegacy migrationを委譲する]
    #   引数: [self: store instance]
    #   戻り値: [dict: settings document]
    #   エラー: [OSError: 未対応schemaの場合]
    # }
    def _load(self):
        return load_settings_document(self.path)

    # {
    #   責務: [_variables: tabからGUI非依存のFeatureSettingsを作る]
    #   処理: [各instance attributeを調べ, 値を取得できるTk variableだけを安定ID付きmappingへ集める]
    #   引数: [tab: variable値を抽出するtab]
    #   戻り値: [FeatureSettings: feature IDとvariable値mapping]
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
        return FeatureSettings(LastSettingsStore._feature_id(tab), values)

    # {
    #   責務: [_feature_id: tabの安定したsettings IDを決定する]
    #   処理: [明示settings_idがあれば使用し, 旧tabは互換のためclass名を返す]
    #   引数: [tab: IDを決めるtab]
    #   戻り値: [str: 永続化用feature ID]
    # }
    @staticmethod
    def _feature_id(tab):
        feature_id = getattr(tab, "settings_id", None)
        if isinstance(feature_id, str) and feature_id.strip():
            return feature_id.strip()
        return STABLE_SETTINGS_IDS.get(type(tab).__name__, type(tab).__name__)
