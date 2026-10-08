import json
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from scripts.widgets.last_settings_store import LastSettingsStore
from scripts.widgets.settings_document import (
    CURRENT_SCHEMA_VERSION,
    load_settings_document,
    save_settings_document,
)
from src.comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings


# {
#   責務: [SettingsDocumentTests: settings documentのversion付与とlegacy移行を検証する]
#   フィールド: []
#   処理: [legacy payloadの移行, versioned payloadの保存, 未対応schemaの拒否を確認する]
# }
class SettingsDocumentTests(TestCase):
    # {
    #   責務: [test_legacy_backend_map_migrates_to_versioned_document: 旧backend mapがversioned documentへ移行されることを検証する]
    #   処理: [legacy JSONを一時fileへ書き, load後のversionとbackend dataを比較する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_legacy_backend_map_migrates_to_versioned_document(self):
        legacy = {"comfyui": {"RandomImageTab": {"var_width": 768}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last_settings.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")

            loaded = load_settings_document(path)

        self.assertEqual(loaded["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertEqual(loaded["backends"], legacy)

    # {
    #   責務: [test_save_writes_versioned_document: saveがversion付きdocumentを保存することを検証する]
    #   処理: [version付きdocumentを一時fileへ保存し, JSON内容を再読込して比較する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_save_writes_versioned_document(self):
        document = {"schema_version": CURRENT_SCHEMA_VERSION, "backends": {"a1111": {}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "last_settings.json"

            save_settings_document(path, document)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document)

    # {
    #   責務: [test_unknown_schema_version_is_not_silently_migrated: 未対応schemaが黙って読み替えられないことを検証する]
    #   処理: [未知versionのJSONを作成し, loadがOSErrorを送出することを確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_unknown_schema_version_is_not_silently_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last_settings.json"
            path.write_text(json.dumps({"schema_version": 999, "backends": {}}), encoding="utf-8")

            with self.assertRaisesRegex(OSError, "未対応"):
                load_settings_document(path)

    # {
    #   責務: [test_last_settings_store_migrates_and_restores_values: legacy設定を保存時に更新し, 既存tabへ復元できることを検証する]
    #   処理: [legacy JSONを用意し, LastSettingsStoreで保存, JSON schemaと復元値を確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_last_settings_store_migrates_and_restores_values(self):
        legacy = {"comfyui": {"SimpleNamespace": {"var_width": 640}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last_settings.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            store = LastSettingsStore("comfyui")
            store.path = path
            source_tab = SimpleNamespace(var_width=tk.IntVar(master=tk.Tcl(), value=768))

            store.save([source_tab])

            payload = json.loads(path.read_text(encoding="utf-8"))
            restored_tab = SimpleNamespace(var_width=tk.IntVar(master=tk.Tcl(), value=0))
            store.restore(restored_tab)

        self.assertEqual(payload["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertEqual(payload["backends"]["comfyui"]["SimpleNamespace"]["var_width"], 768)
        self.assertEqual(restored_tab.var_width.get(), 768)

    # {
    #   責務: [test_explicit_settings_id_migrates_legacy_class_key: 明示IDが旧class名キーを移行して利用することを検証する]
    #   処理: [legacy tab keyの設定を安定ID付きtabで復元し, 保存時に新しいIDへ移す]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_explicit_settings_id_migrates_legacy_class_key(self):
        legacy = {"comfyui": {"SimpleNamespace": {"var_width": 640}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last_settings.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            store = LastSettingsStore("comfyui")
            store.path = path
            tab = SimpleNamespace(
                settings_id="generation.random_image",
                var_width=tk.IntVar(master=tk.Tcl(), value=0),
            )

            store.restore(tab)
            store.save([tab])
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(tab.var_width.get(), 640)
        self.assertNotIn("SimpleNamespace", payload["backends"]["comfyui"])
        self.assertEqual(
            payload["backends"]["comfyui"]["generation.random_image"]["var_width"], 640
        )

    # {
    #   責務: [test_random_image_tab_uses_stable_settings_id: RandomImageTabの旧class名が安定settings IDへ移行されることを検証する]
    #   処理: [旧class名のJSONを読み, tab class名から決定したIDで設定を復元し保存する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_random_image_tab_uses_stable_settings_id(self):
        random_image_tab = type("RandomImageTab", (), {})()
        random_image_tab.var_width = tk.IntVar(master=tk.Tcl(), value=0)
        legacy = {"comfyui": {"RandomImageTab": {"var_width": 896}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last_settings.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            store = LastSettingsStore("comfyui")
            store.path = path

            store.restore(random_image_tab)
            store.save([random_image_tab])
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(random_image_tab.var_width.get(), 896)
        self.assertEqual(
            payload["backends"]["comfyui"]["generation.random_image"]["var_width"], 896
        )

    # {
    #   責務: [test_feature_settings_is_tk_independent_and_read_only: FeatureSettingsがTk型に依存せず値を保持することを検証する]
    #   処理: [通常のPython mappingから生成し, dict変換と内部mappingの変更拒否を確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_feature_settings_is_tk_independent_and_read_only(self):
        settings = FeatureSettings("generation.random_image", {"width": 768})

        self.assertEqual(
            settings.to_dict(), {"feature_id": "generation.random_image", "values": {"width": 768}}
        )
        with self.assertRaises(TypeError):
            settings.values["width"] = 512
