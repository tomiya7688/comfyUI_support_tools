import tkinter as tk

from comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings

from .last_settings_store import LastSettingsStore

STABLE_SETTINGS_IDS = {"RandomImageTab": "generation.random_image"}


# {
#   責務: [TkTabSettingsAdapter: Tk tab変数と純Python FeatureSettingsの間を変換する]
#   フィールド: [store: 設定mappingを永続化する非GUI store]
#   処理: [tabのTk variable値を抽出し, stable IDまたはlegacy tab keyでstoreへ送る]
# }
class TkTabSettingsAdapter:
    # {
    #   責務: [__init__: GUI設定adapterを初期化する]
    #   処理: [純Python settings storeを保持する]
    #   引数: [self: adapter instance, store: 設定永続化store]
    #   戻り値: []
    # }
    def __init__(self, store: LastSettingsStore):
        self.store = store

    # {
    #   責務: [restore: 保存された値をtabのTk variableへ復元する]
    #   処理: [安定IDとlegacy class keyから値を読み, 対応するTk variableだけを更新する]
    #   引数: [self: adapter instance, tab: 値を復元するtab]
    #   戻り値: []
    #   エラー: [OSError: 設定schemaが未対応の場合]
    # }
    def restore(self, tab) -> None:
        feature_id = self._feature_id(tab)
        legacy_key = type(tab).__name__
        try:
            values = self.store.load(feature_id, legacy_key)
        except OSError:
            return
        for name, value in values.items():
            variable = getattr(tab, name, None)
            if not isinstance(variable, tk.Variable):
                continue
            try:
                variable.set(value)
            except (tk.TclError, TypeError, ValueError):
                continue

    # {
    #   責務: [save: tabのTk variable値をsettings storeへ保存する]
    #   処理: [全tabからFeatureSettingsを作り, legacy tab keyとともにstoreへ渡す]
    #   引数: [self: adapter instance, tabs: 設定を保存するtab iterable]
    #   戻り値: []
    #   エラー: [OSError: 設定JSONの読み込みまたは保存に失敗した場合]
    # }
    def save(self, tabs) -> None:
        for tab in tabs:
            settings = self._settings_from_tab(tab)
            self.store.save(settings, type(tab).__name__)

    # {
    #   責務: [_settings_from_tab: Tk tabからFeatureSettingsを作る]
    #   処理: [読み取り可能なTk variable値だけを集め, 安定ID付きsnapshotへ変換する]
    #   引数: [tab: 設定値を取り出すtab]
    #   戻り値: [FeatureSettings: feature IDとtab設定値]
    # }
    @classmethod
    def _settings_from_tab(cls, tab) -> FeatureSettings:
        values = {}
        for name, variable in vars(tab).items():
            if not isinstance(variable, tk.Variable):
                continue
            try:
                values[name] = variable.get()
            except tk.TclError:
                continue
        return FeatureSettings(cls._feature_id(tab), values)

    # {
    #   責務: [_feature_id: tabの安定したsettings IDを決定する]
    #   処理: [明示settings_idがあれば使用し, 旧tabは互換のためclass名を返す]
    #   引数: [tab: IDを決めるtab]
    #   戻り値: [str: 永続化用feature ID]
    # }
    @staticmethod
    def _feature_id(tab) -> str:
        feature_id = getattr(tab, "settings_id", None)
        if isinstance(feature_id, str) and feature_id.strip():
            return feature_id.strip()
        return STABLE_SETTINGS_IDS.get(type(tab).__name__, type(tab).__name__)
