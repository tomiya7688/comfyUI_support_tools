from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.comfyui_support_tools.applications.character_registry.ui.messenger.character_registry_ui_messenger import (
    CharacterRegistryUiMessenger,
)
from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_panel import (
    CharacterRegistryPanel,
)
from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_path_settings_store import (
    CharacterRegistryPathSettingsStore,
)

from ..context import USER_INPUT_DIR, WILDCARDS_DIR


# {
#   責務: [CharacterRegistryTab: 既存Tabbed ToolsへCharacter Registry UIを接続する]
#   フィールド: [panel: 検索・分類確認・登録を行うCharacterRegistryPanel]
# }
class CharacterRegistryTab(ttk.Frame):
    # {
    #   責務: [__init__: Character Registryのcomposition rootを構成する]
    #   処理: [user_data内の設定pathを解決し, API messengerとpanelを接続する]
    #   引数: [self: tab, master: Tk parent]
    #   戻り値: []
    # }
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        settings_path = USER_INPUT_DIR / "config" / "common" / "character_registry.json"
        settings_store = CharacterRegistryPathSettingsStore(settings_path)
        self.panel = CharacterRegistryPanel(
            self,
            CharacterRegistryUiMessenger(),
            settings_store,
            WILDCARDS_DIR,
        )
        self.panel.pack(fill="both", expand=True)
