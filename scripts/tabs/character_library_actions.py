"""Character library actions and profile-state refresh behavior."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import tkinter as tk
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
from comfyui_support_tools.applications.character_registry.process.processing.dataset_readiness import (
    assess_dataset_readiness,
)
from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterProfile,
    CharacterTrait,
    OutfitProfile,
)


# {
#   責務: [CharacterLibraryActions: profile persistenceとtrait/outfit編集actionをpanelから分離する]
#   フィールド: [CharacterLibraryPanelが提供するstate variablesとcontrolsを利用する]
# }
class CharacterLibraryActions:
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
        self._refresh_readiness()

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
        self._refresh_readiness()

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
        self._refresh_readiness()
        self.reload_profiles()

    # {
    #   責務: [_refresh_readiness: selected characterのeffective data readinessをGUIへ表示する]
    #   処理: [selected/effective count、strategy、duplicate/quality warningをsummaryへ反映する]
    #   引数: []
    #   戻り値: []
    # }
    def _refresh_readiness(self) -> None:
        profile = self.current_profile
        if profile is None:
            self.readiness_summary.set("Dataset readiness: save or select a character.")
            return
        readiness = assess_dataset_readiness(profile)
        quality = "unknown" if readiness.mean_quality is None else f"{readiness.mean_quality:.2f}"
        warnings = ", ".join(readiness.warnings) or "none"
        self.readiness_summary.set(
            f"Images: {readiness.selected_image_count} selected / "
            f"{readiness.effective_image_count:.1f} effective · "
            f"strategy: {readiness.suggested_strategy} · "
            f"quality: {quality} · warnings: {warnings}"
        )

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
