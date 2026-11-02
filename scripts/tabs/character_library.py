"""Tk UI for registering characters, outfit traits, and reference images."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from comfyui_support_tools.applications.character_registry.data.processing.image_storage import (
    ImageStorageMode,
)
from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterProfile,
    CharacterTrait,
)
from scripts.tabs.character_library_actions import CharacterLibraryActions


# {
#   責務: [CharacterLibraryPanel: stable IDでCharacter profileを登録/編集しprompt previewを表示する]
#   フィールド: [profile root、選択profile/version、entry variables、library/list/log controls]
# }
class CharacterLibraryPanel(CharacterLibraryActions, ttk.Frame):
    settings_id = "character.library"

    # {
    #   責務: [__init__: Character Library UI controlsとrepository boundaryを構成する]
    #   処理: [1: profile store rootを保存する 2: registration/detail controlsを構築する 3: saved profilesを読み込む]
    #   引数: [master: parent widget, profile_root: persistent character store path]
    #   戻り値: []
    # }
    def __init__(self, master: tk.Misc, profile_root: Path):
        ttk.Frame.__init__(self, master, padding=10)
        self.profile_root = Path(profile_root).expanduser()
        self.current_profile: CharacterProfile | None = None
        self.current_version: str | None = None
        self.character_id = tk.StringVar()
        self.display_name = tk.StringVar()
        self.aliases = tk.StringVar()
        self.trait_category = tk.StringVar()
        self.trait_value = tk.StringVar()
        self.trait_owner = tk.StringVar(value="core")
        self.hidden_trait = tk.BooleanVar(value=False)
        self.trait_refs: list[tuple[str, str, int, CharacterTrait]] = []
        self.outfit_id = tk.StringVar()
        self.outfit_name = tk.StringVar()
        self.set_default_outfit = tk.BooleanVar(value=False)
        self.image_path = tk.StringVar()
        self.image_outfit = tk.StringVar(value="unassigned")
        self.image_storage_mode = tk.StringVar(value=ImageStorageMode.ORIGINAL_AND_WEBP.value)
        self.webp_quality = tk.StringVar(value="92")

        columns = ttk.Frame(self)
        columns.pack(fill="both", expand=True)
        library = ttk.LabelFrame(columns, text="Character Library", padding=8)
        library.pack(side="left", fill="y", padx=(0, 8))
        self.profile_list = tk.Listbox(library, width=28, exportselection=False)
        self.profile_list.pack(fill="y", expand=True)
        self.profile_list.bind("<<ListboxSelect>>", self._on_profile_selected)
        ttk.Button(library, text="Reload", command=self.reload_profiles).pack(fill="x", pady=4)

        detail = ttk.Frame(columns)
        detail.pack(side="left", fill="both", expand=True)
        self._build_identity_panel(detail)
        self._build_outfit_panel(detail)
        self._build_trait_panel(detail)
        self._build_image_panel(detail)
        self._build_prompt_preview(detail)
        self.status = tk.StringVar(
            value="Character data remains local to the selected profile root."
        )
        self.readiness_summary = tk.StringVar(value="Dataset readiness: select a character.")
        ttk.Label(detail, textvariable=self.status, wraplength=700).pack(anchor="w", pady=4)
        self.reload_profiles()

    # {
    #   責務: [_build_identity_panel: stable IDとdisplay nameを編集するidentity欄を構築する]
    #   処理: [name/alias入力、save、new操作をdetailへ追加する]
    #   引数: [detail: right-side editor frame]
    #   戻り値: []
    # }
    def _build_identity_panel(self, detail: ttk.Frame) -> None:
        identity = ttk.LabelFrame(detail, text="Identity", padding=8)
        identity.pack(fill="x")
        self._entry(identity, "Stable character ID", self.character_id)
        self._entry(identity, "Display name", self.display_name)
        self._entry(identity, "Aliases (comma separated)", self.aliases)
        ttk.Button(
            identity,
            text="Create / Save identity",
            command=lambda: self._run_action(self.save_identity),
        ).pack(anchor="e", pady=(4, 0))
        ttk.Button(identity, text="New character", command=self.new_character).pack(anchor="e")

    # {
    #   責務: [_build_outfit_panel: multiple stable outfit profilesを編集する欄を構築する]
    #   処理: [stable ID/name/default choiceとadd actionをdetailへ追加する]
    #   引数: [detail: right-side editor frame]
    #   戻り値: []
    # }
    def _build_outfit_panel(self, detail: ttk.Frame) -> None:
        outfit = ttk.LabelFrame(detail, text="Outfits", padding=8)
        outfit.pack(fill="x", pady=6)
        self._entry(outfit, "Stable outfit ID", self.outfit_id)
        self._entry(outfit, "Outfit name", self.outfit_name)
        ttk.Checkbutton(
            outfit, text="Set as default outfit", variable=self.set_default_outfit
        ).pack(anchor="w")
        ttk.Button(
            outfit, text="Add outfit", command=lambda: self._run_action(self.add_outfit)
        ).pack(anchor="e")

    # {
    #   責務: [_build_trait_panel: core/outfit visible/hidden traitをレビューする欄を構築する]
    #   処理: [owner/category/value controls、trait list、add/edit/reject actionsを追加する]
    #   引数: [detail: right-side editor frame]
    #   戻り値: []
    # }
    def _build_trait_panel(self, detail: ttk.Frame) -> None:
        traits = ttk.LabelFrame(detail, text="Manual trait review", padding=8)
        traits.pack(fill="x")
        self._entry(traits, "Category", self.trait_category)
        self._entry(traits, "Trait", self.trait_value)
        self.owner_combo = ttk.Combobox(
            traits, textvariable=self.trait_owner, values=("core",), state="readonly"
        )
        self.owner_combo.pack(fill="x", pady=3)
        ttk.Checkbutton(traits, text="Hidden / conditional", variable=self.hidden_trait).pack(
            anchor="w"
        )
        ttk.Button(
            traits, text="Add confirmed trait", command=lambda: self._run_action(self.add_trait)
        ).pack(anchor="e")
        self.trait_list = tk.Listbox(traits, height=5, exportselection=False)
        self.trait_list.pack(fill="x", pady=4)
        trait_actions = ttk.Frame(traits)
        trait_actions.pack(fill="x")
        ttk.Button(
            trait_actions,
            text="Edit selected",
            command=lambda: self._run_action(self.edit_selected_trait),
        ).pack(side="left")
        ttk.Button(
            trait_actions,
            text="Reject selected",
            command=lambda: self._run_action(self.reject_selected_trait),
        ).pack(side="left", padx=4)

    # {
    #   責務: [_build_image_panel: reference image登録と保存品質を選べる欄を構築する]
    #   処理: [source/outfit/storage mode/WebP quality controlsと登録actionを追加する]
    #   引数: [detail: right-side editor frame]
    #   戻り値: []
    # }
    def _build_image_panel(self, detail: ttk.Frame) -> None:
        images = ttk.LabelFrame(detail, text="Reference images", padding=8)
        images.pack(fill="x", pady=6)
        self._entry(images, "Image file", self.image_path)
        ttk.Label(images, text="Image outfit").pack(anchor="w")
        self.image_outfit_combo = ttk.Combobox(
            images, textvariable=self.image_outfit, values=("unassigned",), state="readonly"
        )
        self.image_outfit_combo.pack(fill="x", pady=(0, 3))
        ttk.Label(images, text="Storage mode").pack(anchor="w")
        ttk.Combobox(
            images,
            textvariable=self.image_storage_mode,
            values=tuple(mode.value for mode in ImageStorageMode),
            state="readonly",
        ).pack(fill="x", pady=(0, 3))
        self._entry(images, "WebP quality (1..100)", self.webp_quality)
        ttk.Button(
            images,
            text="Register reference image",
            command=lambda: self._run_action(self.register_image),
        ).pack(anchor="e")
        ttk.Label(images, textvariable=self.readiness_summary, wraplength=700).pack(
            anchor="w", pady=(4, 0)
        )

    # {
    #   責務: [_build_prompt_preview: resolved promptをread-onlyで確認する欄を構築する]
    #   処理: [伸縮可能なtext widgetをdetail frameへ追加する]
    #   引数: [detail: right-side editor frame]
    #   戻り値: []
    # }
    def _build_prompt_preview(self, detail: ttk.Frame) -> None:
        preview = ttk.LabelFrame(detail, text="Prompt preview", padding=8)
        preview.pack(fill="both", expand=True)
        self.preview_text = tk.Text(preview, height=5, wrap="word", state="disabled")
        self.preview_text.pack(fill="both", expand=True)

    # {
    #   責務: [_entry: label付きの編集欄をparentへ追加する]
    #   処理: [1: labelを描く 2: linked text entryを作成する]
    #   引数: [parent: target frame, label: visible name, variable: string variable]
    #   戻り値: [entry widget]
    # }
    @staticmethod
    def _entry(parent: ttk.LabelFrame, label: str, variable: tk.StringVar) -> ttk.Entry:
        ttk.Label(parent, text=label).pack(anchor="w")
        entry = ttk.Entry(parent, textvariable=variable)
        entry.pack(fill="x", pady=(0, 3))
        return entry
