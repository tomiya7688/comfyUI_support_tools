from pathlib import Path

from comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings

from .settings_document import load_settings_document, save_settings_document


# {
#   責務: [LastSettingsStore: FeatureSettingsをversioned JSON documentへ保存・復元する]
#   フィールド: [backend: 設定を分離するbackend key, path: 設定JSONの保存先]
#   処理: [Tk変数やTab classを知らずにfeature ID単位の設定mappingを永続化する]
# }
class LastSettingsStore:
    # {
    #   責務: [__init__: backend用settings storeを初期化する]
    #   処理: [backend識別子と注入されたsettings JSON pathを保持する]
    #   引数: [self: store instance, backend: backend識別子, path: 設定JSONの保存先]
    #   戻り値: []
    # }
    def __init__(self, backend: str, path: Path):
        self.backend = backend
        self.path = Path(path)

    # {
    #   責務: [load: feature IDの保存値を読み込む]
    #   処理: [versioned documentからfeature IDを検索し, 必要なら旧tab class keyへfallbackする]
    #   引数: [self: store instance, feature_id: 安定した設定ID, legacy_key: 旧設定のtab class key]
    #   戻り値: [dict: 設定値の独立したmapping]
    #   エラー: [OSError: 未対応schema versionの場合]
    # }
    def load(self, feature_id: str, legacy_key: str | None = None) -> dict:
        backend_values = self._load().get("backends", {}).get(self.backend, {})
        if not isinstance(backend_values, dict):
            return {}
        values = backend_values.get(feature_id)
        if values is None and legacy_key and legacy_key != feature_id:
            values = backend_values.get(legacy_key)
        return dict(values) if isinstance(values, dict) else {}

    # {
    #   責務: [save: FeatureSettingsをfeature ID単位で保存する]
    #   処理: [既存documentを保持し, settings値を更新して不要なlegacy keyを除去する]
    #   引数: [self: store instance, settings: 保存対象の純Python設定, legacy_key: 移行対象の旧tab class key]
    #   戻り値: []
    #   エラー: [OSError: 設定JSONの読み込みまたは保存に失敗した場合]
    # }
    def save(self, settings: FeatureSettings, legacy_key: str | None = None) -> None:
        document = self._load()
        backend_values = document["backends"].setdefault(self.backend, {})
        if not isinstance(backend_values, dict):
            backend_values = {}
            document["backends"][self.backend] = backend_values
        backend_values[settings.feature_id] = settings.to_dict()["values"]
        if legacy_key and legacy_key != settings.feature_id:
            backend_values.pop(legacy_key, None)
        save_settings_document(self.path, document)

    # {
    #   責務: [_load: 設定JSONを現在のversioned documentとして取得する]
    #   処理: [settings document moduleへloadとlegacy migrationを委譲する]
    #   引数: [self: store instance]
    #   戻り値: [dict: settings document]
    #   エラー: [OSError: 未対応schema versionの場合]
    # }
    def _load(self) -> dict:
        return load_settings_document(self.path)
