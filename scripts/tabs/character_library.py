"""Tk UI for registering characters, outfit traits, and reference images."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import ttk
from uuid import uuid4

from comfyui_support_tools.applications.character_registry.data.processing.character_store import (
    character_profile_version,
    list_character_ids,
    load_character_profile,
    save_character_profile,
)
from comfyui_support_tools.applications.character_registry.data.processing.image_storage import (
    ImageStorageMode,
    register_character_image,
)
from comfyui_support_tools.applications.character_registry.process.processing.prompt_resolver import (
    resolve_character_prompt,
    validate_character_profile,
)
from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterProfile,
    CharacterTrait,
    OutfitProfile,
)

from ..context import USER_INPUT_DIR


# {
#   責務: [CharacterLibraryPanel: stable IDでCharacter profileを登録/編集しprompt previewを表示する]
#   フィールド: [profile root、選択profile/version、entry variables、library/list/log controls]
# }
class CharacterLibraryPanel(ttk.Frame):
    # {
    #   責務: [__init__: Character Library UI controlsとrepository boundaryを構成する]
    #   処理: [1: profile store rootとstate variablesを初期化する 2: panel buildersを呼ぶ 3: saved profilesを読み込む]
    #   引数: [master: parent widget, profile_root: persistent character store path]
    #   戻り値: []
    # }
    def __init__(self, master: tk.Misc, profile_root: Path | None = None):
        super().__init__(master, padding=10)
        resolved_root = profile_root or USER_INPUT_DIR / "characters"
        self.profile_root = Path(resolved_root).expanduser()
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
        self._build_layout()
        self.reload_profiles()

    # {
    #   責務: [_build_layout: library paneとeditor paneを組み合わせる]
    #   処理: [1: two-column containerを作る 2: library/editor subpanelsを構築する]
    #   引数: []
    #   戻り値: []
    # }
    def _build_layout(self) -> None:
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
        self._build_preview_panel(detail)

    # {
    #   責務: [_build_identity_panel: stable ID/name/aliasの編集UIを作る]
    #   処理: [1: identity fieldを表示する 2: save/new commandsを接続する]
    #   引数: [detail: character detail parent]
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
    #   責務: [_build_outfit_panel: outfit ID/name/default選択UIを作る]
    #   処理: [1: outfit fieldを表示する 2: default toggleとadd commandを接続する]
    #   引数: [detail: character detail parent]
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
    #   責務: [_build_trait_panel: owner scope/visibilityを含むmanual trait editorを構築する]
    #   処理: [1: trait fieldsとscope selectorを表示する 2: add/edit/reject actionを接続する]
    #   引数: [detail: character detail parent]
    #   戻り値: []
    # }
    def _build_trait_panel(self, detail: ttk.Frame) -> None:
        traits = ttk.LabelFrame(detail, text="Manual trait review", padding=8)
        traits.pack(fill="x")
        self._entry(traits, "Category", self.trait_category)
        self._entry(traits, "Trait", self.trait_value)
        self.owner_combo = ttk.Combobox(
            traits,
            textvariable=self.trait_owner,
            values=("core",),
            state="readonly",
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
    #   責務: [_build_image_panel: source/outfit/storage settingsからimage registration UIを構築する]
    #   処理: [1: image metadata fieldsを表示する 2: storage modeとregister actionを接続する]
    #   引数: [detail: character detail parent]
    #   戻り値: []
    # }
    def _build_image_panel(self, detail: ttk.Frame) -> None:
        images = ttk.LabelFrame(detail, text="Reference images", padding=8)
        images.pack(fill="x", pady=6)
        self._entry(images, "Image file", self.image_path)
        ttk.Label(images, text="Image outfit").pack(anchor="w")
        self.image_outfit_combo = ttk.Combobox(
            images,
            textvariable=self.image_outfit,
            values=("unassigned",),
            state="readonly",
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

    # {
    #   責務: [_build_preview_panel: resolved promptとstatusを表示するreadonly areaを作る]
    #   処理: [1: preview text widgetを作る 2: current status labelを接続する]
    #   引数: [detail: character detail parent]
    #   戻り値: []
    # }
    def _build_preview_panel(self, detail: ttk.Frame) -> None:
        preview = ttk.LabelFrame(detail, text="Prompt preview", padding=8)
        preview.pack(fill="both", expand=True)
        self.preview_text = tk.Text(preview, height=5, wrap="word", state="disabled")
        self.preview_text.pack(fill="both", expand=True)
        self.status = tk.StringVar(
            value="Character data remains local to the selected profile root."
        )
        ttk.Label(detail, textvariable=self.status, wraplength=700).pack(anchor="w", pady=4)

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

    # {
    #   責務: [reload_profiles: valid profile一覧をsafe local storeから表示する]
    #   処理: [1: list idsを取得する 2: typed profileを読み、library lineを再描画する]
    #   引数: []
    #   戻り値: []
    # }
    def reload_profiles(self) -> None:
        self.profile_list.delete(0, tk.END)
        self.profile_ids = list_character_ids(self.profile_root)
        for character_id in self.profile_ids:
            profile = load_character_profile(self.profile_root, character_id)
            self.profile_list.insert(tk.END, f"{profile.display_name}  ·  {character_id}")

    # {
    #   責務: [_on_profile_selected: selected list rowからtyped profile and versionをloadする]
    #   処理: [1: selected row indexを得る 2: profile/version/fields/outfit choicesをrefreshする]
    #   引数: [event: listbox selection event]
    #   戻り値: []
    # }
    def _on_profile_selected(self, _event: tk.Event) -> None:
        selection = self.profile_list.curselection()
        if not selection:
            return
        character_id = self.profile_ids[selection[0]]
        self.current_profile = load_character_profile(self.profile_root, character_id)
        self.current_version = character_profile_version(self.profile_root, character_id)
        self._refresh_selectors()
        self.character_id.set(self.current_profile.character_id)
        self.display_name.set(self.current_profile.display_name)
        self.aliases.set(", ".join(self.current_profile.aliases))
        choices = ("core",) + tuple(item.outfit_id for item in self.current_profile.outfit_profiles)
        self.owner_combo.configure(values=choices)
        self.trait_owner.set(choices[0])
        self.image_outfit_combo.configure(values=("unassigned",) + choices[1:])
        self.image_outfit.set("unassigned")
        self._refresh_trait_list()
        self._refresh_prompt_preview()

    # {
    #   責務: [new_character: editorを新規profile作成状態へ戻す]
    #   処理: [1: current profile/versionをclearする 2: editable character fieldsをresetする]
    #   引数: []
    #   戻り値: []
    # }
    def new_character(self) -> None:
        self.current_profile = None
        self.current_version = None
        self.profile_list.selection_clear(0, tk.END)
        self.character_id.set("")
        self.display_name.set("")
        self.aliases.set("")
        self.image_path.set("")
        self.owner_combo.configure(values=("core",))
        self.trait_owner.set("core")
        self.image_outfit_combo.configure(values=("unassigned",))
        self.image_outfit.set("unassigned")
        self.trait_list.delete(0, tk.END)
        self.trait_refs = []
        self._refresh_prompt_preview()

    # {
    #   責務: [save_identity: new CharacterProfile作成またはstable IDを維持したrenameを保存する]
    #   処理: [1: typed fieldsをvalidateする 2: immutable profileを作る/更新する 3: optimistic storeへsaveする]
    #   引数: []
    #   戻り値: []
    # }
    def save_identity(self) -> None:
        character_id = self.character_id.get().strip()
        name = self.display_name.get().strip()
        if self.current_profile and self.current_profile.character_id != character_id:
            raise ValueError("character_id is immutable after creation")
        if self.current_profile:
            profile = replace(
                self.current_profile,
                display_name=name,
                aliases=tuple(
                    item.strip() for item in self.aliases.get().split(",") if item.strip()
                ),
            )
        else:
            profile = CharacterProfile(
                character_id,
                name,
                aliases=tuple(
                    item.strip() for item in self.aliases.get().split(",") if item.strip()
                ),
            )
            self.current_version = None
        self.current_version = save_character_profile(
            self.profile_root,
            _validated_profile(profile),
            expected_hash=self.current_version,
        )
        self.current_profile = profile
        self.status.set(f"Saved {profile.display_name} ({profile.character_id})")
        self._refresh_selectors()
        self._refresh_trait_list()
        self._refresh_prompt_preview()
        self.reload_profiles()

    # {
    #   責務: [_run_action: UI commandのvalidation/storage errorをstatusへ表示する]
    #   処理: [1: actionを実行する 2: success/errorを可視statusへ反映する]
    #   引数: [action: zero-argument UI command]
    #   戻り値: []
    # }
    def _run_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as error:
            self.status.set(f"{type(error).__name__}: {error}")

    # {
    #   責務: [add_outfit: selected characterへ衣装profileを追加して保存する]
    #   処理: [1: current profile/inputsを確認する 2: stable outfit IDを追加する 3: versioned profileを保存する]
    #   引数: []
    #   戻り値: []
    # }
    def add_outfit(self) -> None:
        profile = self._require_profile()
        new_outfit = OutfitProfile(
            self.outfit_id.get().strip(),
            self.outfit_name.get().strip(),
            is_default=self.set_default_outfit.get(),
        )
        outfits = tuple(
            replace(item, is_default=False) if new_outfit.is_default else item
            for item in profile.outfit_profiles
        ) + (new_outfit,)
        updated = replace(
            profile,
            outfit_profiles=outfits,
            default_outfit_id=new_outfit.outfit_id
            if new_outfit.is_default
            else profile.default_outfit_id,
        )
        self._save_updated_profile(updated)

    # {
    #   責務: [add_trait: user-confirmed traitをcoreまたはselected outfitへ登録する]
    #   処理: [1: trait contractを作る 2: owner/hidden choiceに応じたfieldだけ更新する 3: optimistic saveする]
    #   引数: []
    #   戻り値: []
    # }
    def add_trait(self) -> None:
        profile = self._require_profile()
        trait = CharacterTrait(self.trait_category.get().strip(), self.trait_value.get().strip())
        owner = self.trait_owner.get()
        if owner == "core":
            if self.hidden_trait.get():
                raise ValueError("hidden traits must belong to an outfit")
            updated = replace(profile, core_traits=profile.core_traits + (trait,))
        else:
            outfit = next(item for item in profile.outfit_profiles if item.outfit_id == owner)
            field_name = "hidden_traits" if self.hidden_trait.get() else "traits"
            values = getattr(outfit, field_name) + (trait,)
            updated_outfit = replace(outfit, **{field_name: values, "user_confirmed": True})
            updated = replace(
                profile,
                outfit_profiles=tuple(
                    updated_outfit if item.outfit_id == owner else item
                    for item in profile.outfit_profiles
                ),
            )
        self._save_updated_profile(updated)

    # {
    #   責務: [edit_selected_trait: selected core/outfit traitを手動修正する]
    #   処理: [1: trait row referenceを解決する 2: category/valueを反映する 3: immutable profileを保存する]
    #   引数: []
    #   戻り値: []
    # }
    def edit_selected_trait(self) -> None:
        profile = self._require_profile()
        selection = self.trait_list.curselection()
        if not selection:
            raise ValueError("select a trait to edit")
        kind, owner, index, trait = self.trait_refs[selection[0]]
        updated_trait = replace(
            trait,
            category=self.trait_category.get().strip(),
            value=self.trait_value.get().strip(),
            source="user_confirmed",
        )
        updated = self._replace_trait(profile, kind, owner, index, updated_trait)
        self._save_updated_profile(updated)

    # {
    #   責務: [reject_selected_trait: selected traitをpromptから外しrejected listへ残す]
    #   処理: [1: selected traitを解決する 2: active trait setから除く 3: audit可能なrejected traitとして保存する]
    #   引数: []
    #   戻り値: []
    # }
    def reject_selected_trait(self) -> None:
        profile = self._require_profile()
        selection = self.trait_list.curselection()
        if not selection:
            raise ValueError("select a trait to reject")
        kind, owner, index, trait = self.trait_refs[selection[0]]
        updated = self._replace_trait(profile, kind, owner, index, None)
        updated = replace(
            updated,
            rejected_traits=updated.rejected_traits + (replace(trait, source="user_rejected"),),
        )
        self._save_updated_profile(updated)

    # {
    #   責務: [register_image: original sourceを検証してWebP previewと共にprofileへ登録する]
    #   処理: [1: source pathとprofileを確認する 2: imageを管理保存する 3: optimistic profile updateする]
    #   引数: []
    #   戻り値: []
    # }
    def register_image(self) -> None:
        profile = self._require_profile()
        image_id = f"image_{uuid4().hex}"
        registered = register_character_image(
            Path(self.image_path.get().strip()),
            self.profile_root / profile.character_id / "images",
            image_id,
            mode=ImageStorageMode(self.image_storage_mode.get()),
            outfit_id=(
                self.image_outfit.get() if self.image_outfit.get() != "unassigned" else None
            ),
            webp_quality=int(self.webp_quality.get()),
            known_images=profile.image_refs,
        )
        self._save_updated_profile(replace(profile, image_refs=profile.image_refs + (registered,)))

    # {
    #   責務: [_require_profile: selected/entered profileが保存済みか検証する]
    #   処理: [1: current_profileを確認する 2: absent時に明確なvalidation errorを返す]
    #   引数: []
    #   戻り値: [CharacterProfile]
    # }
    def _require_profile(self) -> CharacterProfile:
        if self.current_profile is None:
            raise ValueError("create or select a character first")
        return self.current_profile

    # {
    #   責務: [_save_updated_profile: expected versionを使ってprofile editを保存する]
    #   処理: [1: loaded versionを確認する 2: write tokenを更新する 3: selected profile/list/previewをrefreshする]
    #   引数: [profile: immutable profile replacement]
    #   戻り値: []
    # }
    def _save_updated_profile(self, profile: CharacterProfile) -> None:
        self.current_version = save_character_profile(
            self.profile_root,
            _validated_profile(profile),
            expected_hash=self.current_version,
        )
        self.current_profile = profile
        self._refresh_selectors()
        self._refresh_trait_list()
        self._refresh_prompt_preview()
        self.reload_profiles()

    # {
    #   責務: [_refresh_selectors: current profile outfit IDsをtrait/image selectorへ反映する]
    #   処理: [1: core/outfit choicesを生成する 2: owner/image combo valuesを更新する]
    #   引数: []
    #   戻り値: []
    # }
    def _refresh_selectors(self) -> None:
        profile = self.current_profile
        outfit_ids = tuple(item.outfit_id for item in profile.outfit_profiles) if profile else ()
        self.owner_combo.configure(values=("core",) + outfit_ids)
        if self.trait_owner.get() not in {"core", *outfit_ids}:
            self.trait_owner.set("core")
        self.image_outfit_combo.configure(values=("unassigned",) + outfit_ids)
        if self.image_outfit.get() not in {"unassigned", *outfit_ids}:
            self.image_outfit.set("unassigned")

    # {
    #   責務: [_replace_trait: core/outfit visible/hidden trait tupleをindex指定でimmutable更新する]
    #   処理: [1: ownerから対象tupleを選ぶ 2: item replace/removeする 3: ownerのprofileを再構築する]
    #   引数: [profile: selected profile, kind: storage scope, owner: outfit ID, index: trait index, replacement: new trait or None]
    #   戻り値: [CharacterProfile]
    # }
    @staticmethod
    def _replace_trait(
        profile: CharacterProfile,
        kind: str,
        owner: str,
        index: int,
        replacement: CharacterTrait | None,
    ) -> CharacterProfile:
        # {
        #   責務: [changed: trait tupleの指定indexだけをreplace/removeする]
        #   処理: [1: 対象より前を保持する 2: replacementがあれば追加する 3: 後続を保持する]
        #   引数: [values: existing trait tuple]
        #   戻り値: [new trait tuple]
        # }
        def changed(values: tuple[CharacterTrait, ...]) -> tuple[CharacterTrait, ...]:
            return values[:index] + ((replacement,) if replacement else ()) + values[index + 1 :]

        if kind == "core":
            return replace(profile, core_traits=changed(profile.core_traits))
        if kind == "rejected":
            return replace(profile, rejected_traits=changed(profile.rejected_traits))
        outfits = []
        for outfit in profile.outfit_profiles:
            if outfit.outfit_id != owner:
                outfits.append(outfit)
                continue
            field_name = "hidden_traits" if kind == "hidden" else "traits"
            outfits.append(replace(outfit, **{field_name: changed(getattr(outfit, field_name))}))
        return replace(profile, outfit_profiles=tuple(outfits))

    # {
    #   責務: [_refresh_trait_list: current core/outfit traitsを編集可能なstable rowへ表示する]
    #   処理: [1: row mappingをresetする 2: core/outfit/hidden traitsを一意順で描画する]
    #   引数: []
    #   戻り値: []
    # }
    def _refresh_trait_list(self) -> None:
        profile = self.current_profile
        self.trait_list.delete(0, tk.END)
        self.trait_refs = []
        if profile is None:
            return
        collections = [
            ("core", "core", profile.core_traits),
            ("rejected", "rejected", profile.rejected_traits),
        ]
        for outfit in profile.outfit_profiles:
            collections.append(("outfit", outfit.outfit_id, outfit.traits))
            collections.append(("hidden", outfit.outfit_id, outfit.hidden_traits))
        for kind, owner, values in collections:
            for index, trait in enumerate(values):
                self.trait_refs.append((kind, owner, index, trait))
                self.trait_list.insert(tk.END, f"{kind}/{owner}: {trait.category} = {trait.value}")

    # {
    #   責務: [_refresh_prompt_preview: core/default-outfit traitsを解決してpreviewへ表示する]
    #   処理: [1: prompt resolverを呼ぶ 2: resolved traitとvisible hidden decisionをreadonly textへ表示する]
    #   引数: []
    #   戻り値: []
    # }
    def _refresh_prompt_preview(self) -> None:
        profile = self.current_profile
        if profile is None:
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.configure(state="disabled")
            return
        result = resolve_character_prompt(profile)
        hidden = [
            f"{item.attribute}: {item.action} ({', '.join(item.reasons)})"
            for item in result.hidden_decisions
        ]
        lines = list(result.traits) + hidden
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", "\n".join(lines))
        self.preview_text.configure(state="disabled")


# {
#   責務: [_validated_profile: UIから渡すprofileをprocess contractで検証して返す]
#   処理: [1: pure profile validationを実行する 2: valid profileを返す]
#   引数: [profile: candidate CharacterProfile]
#   戻り値: [validated CharacterProfile]
# }
def _validated_profile(profile: CharacterProfile) -> CharacterProfile:
    validate_character_profile(profile)
    return profile
