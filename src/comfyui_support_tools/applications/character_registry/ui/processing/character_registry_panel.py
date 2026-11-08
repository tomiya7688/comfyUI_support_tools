from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, simpledialog, ttk

from src.comfyui_support_tools.applications.character_registry.ui.messenger.character_registry_ui_messenger import (
    CharacterRegistryUiMessenger,
)
from src.comfyui_support_tools.applications.character_registry.ui.processing.character_reference_image_statistics import (
    format_reference_image_statistics,
)
from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_panel_view import (
    CharacterRegistryPanelView,
)
from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_path_settings_store import (
    CharacterRegistryPathSettingsStore,
)
from src.comfyui_support_tools.shared.contracts.character_id import create_character_id
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings


# {
#   責務: [_write_wildcards_and_describe: 登録profileのwildcard bundleを出力し結果説明を返す]
#   処理: [public messengerへ書き出しを依頼し, 成功/失敗とprofile登録済み状態を文面化する]
#   引数: [messenger: API, profile: 登録profile, wildcard_root: 出力root]
#   戻り値: [tuple[bool, str]: export succeeded and UI status message]
# }
def _write_wildcards_and_describe(
    messenger: CharacterRegistryUiMessenger,
    profile: CharacterProfile,
    wildcard_root: Path,
) -> tuple[bool, str]:
    """Write a saved profile's wildcard bundle and describe local LoRA mapping state."""
    try:
        written_paths = messenger.write_character_wildcard_files(profile, wildcard_root)
    except Exception as error:
        return False, (
            f"{profile.display_name}は登録済みですがwildcard出力に失敗しました。"
            f"「wildcard出力を再試行」できます。{type(error).__name__}: {error}"
        )
    lora_call_file = wildcard_root / "anime_character_lora" / f"{profile.character_id}.txt"
    status = (
        f"登録しました: {profile.display_name} ({profile.character_id})。"
        f"wildcard {len(written_paths)}件を {wildcard_root} へ出力しました。"
    )
    if not lora_call_file.is_file():
        status += (
            f" 対応LoRAは未設定です。生成前に {lora_call_file} を作成し、"
            "そこへLoRA呼び出しを記述してください。"
        )
    return True, status


# {
#   責務: [CharacterRegistryPanel: Civitai/local caption intakeの検索,分類確認,登録UIを表示する]
#   フィールド: [UI widgets, path/Tagger settings, selected candidates, preview, async request queue]
# }
class CharacterRegistryPanel(ttk.Frame):
    """Manual Character intake view. Civitai weights and images are never downloaded."""

    # {
    #   責務: [__init__: Character Registry intake UIと設定状態を初期化する]
    #   処理: [settingsを読み込み, widgetsを構築して空のCharacter IDを生成する]
    #   引数: [self: panel, master: Tk parent, messenger: application API boundary, settings_store: path settings]
    #   戻り値: []
    # }
    def __init__(
        self,
        master: tk.Misc,
        messenger: CharacterRegistryUiMessenger,
        settings_store: CharacterRegistryPathSettingsStore,
        wildcard_root: Path,
    ) -> None:
        super().__init__(master, padding=12)
        self.messenger = messenger
        self.settings_store = settings_store
        self.wildcard_root = Path(wildcard_root)
        self.candidates: tuple[CivitaiLoraCandidate, ...] = ()
        self.preview: CharacterTagIntakePreview | None = None
        self._preview_request: CharacterTagIntakeRequest | None = None
        self._preview_candidate: CivitaiLoraCandidate | None = None
        self.identity_tags: list[str] = []
        self.outfit_tags: list[str] = []
        self.innerwear_tags: list[str] = []
        self.confirmed_outfits: list[CharacterOutfitProfile] = []
        self.reference_images: list[CharacterReferenceImage] = []
        self._candidate_query = ""
        self._candidate_next_cursor: str | None = None
        self._registered_profile: CharacterProfile | None = None
        self._wildcard_retry_enabled = False
        self._task_results: Queue[tuple[bool, object]] = Queue()
        self._task_pending = False
        self.status = tk.StringVar(value="caption folderを選び、previewを作成してください。")
        try:
            settings = self.settings_store.load()
        except ValueError as error:
            settings = {
                "dataset_root": "",
                "profile_directory": "",
                "tagger_url": "http://127.0.0.1:7861/pixai/v1/interrogate",
                "tagger_model": "",
            }
            self.status.set(f"保存済みpath設定を読み込めません: {error}")
        self.character_id = tk.StringVar(value=create_character_id())
        self.display_name = tk.StringVar()
        self.aliases = tk.StringVar()
        self.dataset_root = tk.StringVar(value=settings["dataset_root"])
        self.profile_directory = tk.StringVar(value=settings["profile_directory"])
        self.tagger_url = tk.StringVar(value=settings["tagger_url"])
        self.tagger_model = tk.StringVar(value=settings["tagger_model"])
        self.analyze_civitai_images = tk.StringVar(value="0")
        self.civitai_query = tk.StringVar()
        self.outfit_id = tk.StringVar(value="default")
        self.outfit_name = tk.StringVar(value="Default Outfit")
        self.default_outfit_id = tk.StringVar(value="")
        self.reference_image_assignment = tk.StringVar(value="")
        self.reference_image_statistics = tk.StringVar(value=format_reference_image_statistics(()))
        self._reference_image_assignment_choices: dict[str, tuple[str, str | None]] = {}
        variables = {
            "dataset_root": self.dataset_root,
            "profile_directory": self.profile_directory,
            "tagger_url": self.tagger_url,
            "tagger_model": self.tagger_model,
            "analyze_civitai_images": self.analyze_civitai_images,
            "character_id": self.character_id,
            "display_name": self.display_name,
            "aliases": self.aliases,
            "civitai_query": self.civitai_query,
            "outfit_id": self.outfit_id,
            "outfit_name": self.outfit_name,
            "default_outfit_id": self.default_outfit_id,
            "reference_image_assignment": self.reference_image_assignment,
            "reference_image_statistics": self.reference_image_statistics,
            "status": self.status,
        }
        actions = {
            "choose_dataset": self._choose_dataset,
            "choose_profile_directory": self._choose_profile_directory,
            "regenerate_id": self._regenerate_character_id,
            "search_civitai": self.search_civitai,
            "next_civitai_page": self.next_civitai_page,
            "preview_intake": self.preview_intake,
            "add_identity": self._add_identity,
            "add_outfit": self._add_outfit,
            "add_innerwear": self._add_innerwear,
            "remove_identity": self._remove_identity,
            "remove_outfit": self._remove_outfit,
            "remove_innerwear": self._remove_innerwear,
            "add_custom_tag": self._add_custom_tag,
            "save_outfit_profile": self._save_outfit_profile,
            "delete_outfit_profile": self._delete_outfit_profile,
            "register_profile": self.register_profile,
            "retry_wildcard_export": self.retry_wildcard_export,
            "save_lora_call_wildcard": self.save_lora_call_wildcard,
            "add_reference_images": self.add_reference_images,
            "remove_reference_images": self.remove_reference_images,
            "select_reference_image": self._select_reference_image,
            "assign_reference_image": self._assign_reference_image,
        }
        self.view = CharacterRegistryPanelView(self, variables, actions)
        self.view.pack(fill="both", expand=True)
        self.candidate_list = self.view.candidate_list
        self.suggestion_list = self.view.suggestion_list
        self.saved_outfit_list = self.view.saved_outfit_list
        self.reference_image_list = self.view.reference_image_list
        self.add_reference_images_button = self.view.add_reference_images_button
        self.remove_reference_images_button = self.view.remove_reference_images_button
        self.reference_image_assignment_combo = self.view.reference_image_assignment_combo
        self.assign_reference_image_button = self.view.assign_reference_image_button
        self.default_outfit_combo = self.view.default_outfit_combo
        self.identity_list = self.view.identity_list
        self.outfit_list = self.view.outfit_list
        self.innerwear_list = self.view.innerwear_list
        self.search_button = self.view.search_button
        self.next_page_button = self.view.next_page_button
        self.preview_button = self.view.preview_button
        self.register_button = self.view.register_button
        self.wildcard_retry_button = self.view.wildcard_retry_button
        self._render_saved_outfits()

    # {
    #   責務: [_choose_dataset: Tagger captionを含むdataset folderを選択する]
    #   処理: [folder picker結果を変数へ設定し, path設定を保存する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _choose_dataset(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="caption dataset folderを選択")
        if selected:
            self.dataset_root.set(selected)
            self._save_paths()

    # {
    #   責務: [_choose_profile_directory: CharacterProfile保存directoryを選択する]
    #   処理: [folder picker結果を変数へ設定し, path設定を保存する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _choose_profile_directory(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="Character profile保存先を選択")
        if selected:
            self.profile_directory.set(selected)
            self._save_paths()

    # {
    #   責務: [_save_paths: 最終選択したdataset/profile pathsをuser_data設定へ保存する]
    #   処理: [settings storeへ二つのpathを渡す]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _save_paths(self) -> bool:
        """Persist both editable path fields, reporting errors to the status line."""
        try:
            self.settings_store.save(
                self.dataset_root.get().strip(),
                self.profile_directory.get().strip(),
                self.tagger_url.get().strip(),
                self.tagger_model.get().strip(),
            )
            self.status.set("path設定を保存しました。")
            return True
        except (OSError, ValueError) as error:
            self.status.set(f"path設定の保存に失敗: {error}")
            return False

    # {
    #   責務: [_regenerate_character_id: まだ登録していないCharacter IDを再生成する]
    #   処理: [stable ID generatorの結果をID欄へ設定する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _regenerate_character_id(self) -> None:
        self.character_id.set(create_character_id())

    # {
    #   責務: [search_civitai: Civitai検索結果を非同期で取得して候補欄へ表示する]
    #   処理: [空検索を拒否し, messenger検索をworker threadへ依頼する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def search_civitai(self) -> None:
        """Start a fresh Civitai model/version metadata search for the current query."""
        query = self.civitai_query.get().strip()
        if not query:
            self.status.set("Civitaiの検索語を入力してください。")
            return
        self._candidate_query = query
        self._candidate_next_cursor = None
        self.next_page_button.configure(state="disabled")
        self._start_task(
            "Civitai候補を検索中...",
            lambda: self.messenger.search_civitai_loras(query),
            self._show_candidates,
        )

    # {
    #   責務: [next_civitai_page: 現在のCivitai検索の次ページを追加取得する]
    #   処理: [保持中のquery/cursorをAPIへ渡し, 検索候補へ追加する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def next_civitai_page(self) -> None:
        """Append the next page of candidates for the current Civitai query."""
        cursor = self._candidate_next_cursor
        if not self._candidate_query or not cursor:
            self.status.set("次のCivitai候補はありません。")
            return
        self._candidate_next_cursor = None
        self.next_page_button.configure(state="disabled")
        self._start_task(
            "Civitaiの次ページを取得中...",
            lambda: self.messenger.search_civitai_loras(self._candidate_query, cursor),
            lambda result: self._show_candidates(result, append=True),
        )

    # {
    #   責務: [_show_candidates: Civitai検索結果を選択可能な候補欄へ描画する]
    #   処理: [candidate tupleを保持し, model/version/creatorをlistboxへ表示する]
    #   引数: [self: panel, result: 候補一覧と次cursor]
    #   戻り値: []
    # }
    def _show_candidates(
        self,
        result: tuple[tuple[CivitaiLoraCandidate, ...], str | None],
        *,
        append: bool = False,
    ) -> None:
        """Display candidates and retain the opaque cursor for pagination."""
        candidates, self._candidate_next_cursor = result
        current_candidates = list(self.candidates) if append else []
        known_versions = {(item.model_id, item.version_id) for item in current_candidates}
        new_candidates = [
            candidate
            for candidate in candidates
            if (candidate.model_id, candidate.version_id) not in known_versions
        ]
        current_candidates.extend(new_candidates)
        self.candidates = tuple(current_candidates)
        if not append:
            self.candidate_list.delete(0, "end")
        for candidate in new_candidates:
            creator = candidate.creator or "作者不明"
            self.candidate_list.insert(
                "end",
                f"{candidate.model_name} / {candidate.version_name} — {creator} / {candidate.base_model}",
            )
        self.next_page_button.configure(
            state="normal" if self._candidate_next_cursor else "disabled"
        )
        self.status.set(
            f"Civitai候補: {len(self.candidates)}件。選択は任意です。"
            if not self._candidate_next_cursor
            else f"Civitai候補: {len(self.candidates)}件。次ページを取得できます。"
        )

    # {
    #   責務: [_selected_candidate: candidate listboxの選択versionを返す]
    #   処理: [single selection indexを型付きcandidateへ変換する]
    #   引数: [self: panel]
    #   戻り値: [CivitaiLoraCandidate | None: 選択LoRA version]
    # }
    def _selected_candidate(self) -> CivitaiLoraCandidate | None:
        selected = self.candidate_list.curselection()
        return self.candidates[selected[0]] if selected else None

    # {
    #   責務: [preview_intake: local captionと任意Civitai metadataのtag previewを作る]
    #   処理: [formをvalidateし, selected candidateと任意Tagger設定を指定して非同期previewする]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def preview_intake(self) -> None:
        """Validate and persist the form before asynchronously creating a preview."""
        try:
            request = self._build_request()
        except ValueError as error:
            self.status.set(str(error))
            return
        if not self._save_paths():
            return
        candidate = self._selected_candidate()
        tagger_settings = None
        if candidate is not None and self.analyze_civitai_images.get() == "1":
            tagger_settings = TaggerSettings(
                url=self.tagger_url.get().strip(),
                model=self.tagger_model.get().strip(),
                threshold=0.35,
                character_threshold=0.85,
                timeout=30,
                backend="auto_http",
            )
        self._start_task(
            "captionとTagger候補を確認中...",
            lambda: (
                request,
                candidate,
                self.messenger.preview_character_intake(request, candidate, tagger_settings),
            ),
            self._show_preview_result,
        )

    # {
    #   責務: [_show_preview_result: previewとその入力snapshotをcontroller stateへ保存する]
    #   処理: [request/candidateを保持して, previewを画面へ描画する]
    #   引数: [self: panel, result: request/candidate/previewのtuple]
    #   戻り値: []
    # }
    def _show_preview_result(
        self,
        result: tuple[
            CharacterTagIntakeRequest,
            CivitaiLoraCandidate | None,
            CharacterTagIntakePreview,
        ],
    ) -> None:
        """Keep the exact request snapshot that produced the displayed preview."""
        self._preview_request, self._preview_candidate, preview = result
        self._show_preview(preview)

    # {
    #   責務: [_build_request: form inputからCharacterTagIntakeRequestを作る]
    #   処理: [ID/name/dataset directoryを検証し, aliasesを区切ってrequestにする]
    #   引数: [self: panel]
    #   戻り値: [CharacterTagIntakeRequest: API request]
    #   エラー: [ValueError: 必須inputが空またはdatasetが存在しない場合]
    # }
    def _build_request(self) -> CharacterTagIntakeRequest:
        """Build a request after validating non-empty form values and dataset path."""
        dataset_value = self.dataset_root.get().strip()
        if not dataset_value:
            raise ValueError("caption folderを選択してください。")
        dataset_root = Path(dataset_value).expanduser()
        character_id = self.character_id.get().strip()
        display_name = self.display_name.get().strip()
        if not character_id or not display_name:
            raise ValueError("stable IDと表示名を入力してください。")
        if not dataset_root.is_dir():
            raise ValueError("caption folderを選択してください。")
        aliases = tuple(alias.strip() for alias in self.aliases.get().split(",") if alias.strip())
        return CharacterTagIntakeRequest(character_id, display_name, aliases, dataset_root)

    # {
    #   責務: [_show_preview: taxonomy previewを表示し, manual reviewを初期化する]
    #   処理: [4 categoryのtag/source/confidenceとwarningsを表示する]
    #   引数: [self: panel, preview: APIから返ったclassification preview]
    #   戻り値: []
    # }
    def _show_preview(self, preview: CharacterTagIntakePreview) -> None:
        """Render suggestions and reset all manual classification lists."""
        self.preview = preview
        self.identity_tags.clear()
        self.outfit_tags.clear()
        self.innerwear_tags.clear()
        self.confirmed_outfits.clear()
        self._render_saved_outfits()
        self.outfit_id.set("default")
        self.outfit_name.set("Default Outfit")
        self._render_confirmed_tags()
        self.suggestion_list.delete(0, "end")
        self._suggestions: list[str] = []
        for category, candidates in (
            ("identity", preview.identity_candidates),
            ("outfit", tuple(tag for group in preview.outfit_groups for tag in group.tags)),
            ("context", preview.context_candidates),
            ("unclassified", preview.unclassified_candidates),
        ):
            for candidate in candidates:
                label = f"[{category}] {candidate.tag} ({candidate.count})"
                self._suggestions.append(candidate.tag)
                self.suggestion_list.insert("end", label)
        warnings = " / ".join(preview.warnings) if preview.warnings else "追加の警告はありません。"
        self.status.set(
            f"preview ready: {len(self._suggestions)}候補。分類は未確認です。 {warnings}"
        )

    # {
    #   責務: [_add_identity: 選択候補を手動確認済みidentityへ追加する]
    #   処理: [選択tagを重複除去してidentityへ移動する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _add_identity(self) -> None:
        self._add_selected_tags(self.identity_tags)
        self._render_confirmed_tags()

    # {
    #   責務: [_add_outfit: 選択候補を手動確認済みoutfitへ追加する]
    #   処理: [選択tagを重複除去してoutfitへ移動する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _add_outfit(self) -> None:
        self._add_selected_tags(self.outfit_tags)
        self._render_confirmed_tags()

    # {
    #   責務: [_add_innerwear: 選択候補を通常promptへ出さないinnerwearへ追加する]
    #   処理: [選択tagを重複除去してhidden innerwearへ移動する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _add_innerwear(self) -> None:
        """Move selected suggestions into the non-default innerwear category."""
        self._add_selected_tags(self.innerwear_tags)
        self._render_confirmed_tags()

    # {
    #   責務: [_add_selected_tags: preview selectionを指定されたconfirmed tag listに追加する]
    #   処理: [選択行indexからtagを抽出し, 未登録tagだけをappendする]
    #   引数: [self: panel, destination: 手動確認済みtag list]
    #   戻り値: []
    # }
    def _add_selected_tags(self, destination: list[str]) -> None:
        for index in self.suggestion_list.curselection():
            tag = self._suggestions[index]
            if tag not in destination:
                destination.append(tag)

    # {
    #   責務: [_remove_identity: 選択済みidentity tagを登録候補から外す]
    #   処理: [selected identity listbox rowsを逆順に削除する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _remove_identity(self) -> None:
        self._remove_selected_tags(self.identity_tags, self.identity_list)

    # {
    #   責務: [_remove_outfit: 選択済みoutfit tagを登録候補から外す]
    #   処理: [selected outfit listbox rowsを逆順に削除する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _remove_outfit(self) -> None:
        self._remove_selected_tags(self.outfit_tags, self.outfit_list)

    # {
    #   責務: [_remove_innerwear: 選択済みinnerwearを確認内容から外す]
    #   処理: [selected innerwear rowsを逆順に削除する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _remove_innerwear(self) -> None:
        """Remove selected hidden innerwear traits from the confirmation."""
        self._remove_selected_tags(self.innerwear_tags, self.innerwear_list)

    # {
    #   責務: [_remove_selected_tags: selected tagをconfirmed listから削除する]
    #   処理: [選択indexを逆順に削除し, listboxを再描画する]
    #   引数: [self: panel, tags: 対象tag list, listing: 対象listbox]
    #   戻り値: []
    # }
    def _remove_selected_tags(self, tags: list[str], listing: tk.Listbox) -> None:
        for index in reversed(listing.curselection()):
            del tags[index]
        self._render_confirmed_tags()

    # {
    #   責務: [_render_confirmed_tags: 確認済みidentity/outfit/innerwearをlistboxへ反映する]
    #   処理: [3 listsをtag順のまま再描画する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _render_confirmed_tags(self) -> None:
        for listing, tags in (
            (self.identity_list, self.identity_tags),
            (self.outfit_list, self.outfit_tags),
            (self.innerwear_list, self.innerwear_tags),
        ):
            listing.delete(0, "end")
            for tag in tags:
                listing.insert("end", tag)

    # {
    #   責務: [_add_custom_tag: previewに無い手動修正tagをidentity/outfit/innerwearへ追加する]
    #   処理: [userのcategoryとcustom textを確認してtag listへ追加する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _add_custom_tag(self) -> None:
        """Add a manually entered tag to the selected confirmation category."""
        value = simpledialog.askstring("Custom tag", "追加するtagを入力してください。", parent=self)
        if not value:
            return
        category = simpledialog.askstring(
            "分類先", "identity / outfit / innerwear のいずれかを入力してください。", parent=self
        )
        destination = {
            "identity": self.identity_tags,
            "outfit": self.outfit_tags,
            "innerwear": self.innerwear_tags,
        }.get((category or "").strip().lower())
        if destination is None:
            self.status.set("分類先にはidentity / outfit / innerwearを指定してください。")
            return
        self._append_tags(destination, value)
        self._render_confirmed_tags()

    # {
    #   責務: [_append_tags: comma/newline区切りのmanual tagを重複なく追加する]
    #   処理: [入力をtagへ分割し, 空値と既存tagを除いて追加する]
    #   引数: [tags: destination list, text: user text]
    #   戻り値: []
    # }
    @staticmethod
    def _append_tags(tags: list[str], text: str) -> None:
        for token in text.replace("\n", ",").split(","):
            value = token.strip()
            if value and value not in tags:
                tags.append(value)

    # {
    #   責務: [register_profile: 手動で振り分けたtrait/outfitをprofile登録する]
    #   処理: [confirmationと保存rootを検証し, API登録をworkerへ依頼する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def register_profile(self) -> None:
        """Register only when the current form still matches the shown preview."""
        if self.preview is None:
            self.status.set("先にtag previewを作成してください。")
            return
        try:
            current_request = self._build_request()
        except ValueError as error:
            self.status.set(str(error))
            return
        if (
            current_request != self._preview_request
            or self._selected_candidate() != self._preview_candidate
        ):
            self.status.set(
                "ID・表示名・別名・caption folderまたはCivitai候補が変わりました。previewを作り直してください。"
            )
            return
        if not self.identity_tags:
            self.status.set("登録するidentity tagを選択してください。")
            return
        profile_directory = Path(self.profile_directory.get().strip()).expanduser()
        if not profile_directory.is_absolute():
            self.status.set("profile folderを選択してください。")
            return
        if not self._save_paths():
            return
        try:
            confirmation = self._build_confirmation()
        except ValueError as error:
            self.status.set(str(error))
            return
        preview = self.preview
        self._start_task(
            "CharacterProfileを保存中...",
            lambda: self.messenger.register_character_intake(
                preview, confirmation, profile_directory
            ),
            self._show_registered_profile,
        )

    # {
    #   責務: [_save_outfit_profile: 現在の衣装分類を確認済みoutfitとして積む]
    #   処理: [衣装ID/名前/traitを検証し, profile listへ追加してdefault未選択なら既定にする]
    #   引数: [self: panel]
    #   戻り値: []
    #   状態: [status: 入力不足または重複IDの説明を表示する]
    # }
    def _save_outfit_profile(self) -> None:
        outfit_id = self.outfit_id.get().strip()
        outfit_name = self.outfit_name.get().strip()
        if not outfit_id or not outfit_name:
            self.status.set("衣装IDと衣装名を入力してください。")
            return
        if not self.outfit_tags and not self.innerwear_tags:
            self.status.set("衣装またはinnerwearのtagを追加してください。")
            return
        if any(outfit.outfit_id == outfit_id for outfit in self.confirmed_outfits):
            self.status.set(f"衣装ID「{outfit_id}」はすでに登録候補にあります。")
            return
        self.confirmed_outfits.append(
            CharacterOutfitProfile(
                outfit_id=outfit_id,
                name=outfit_name,
                garment_traits=tuple(self.outfit_tags),
                innerwear_traits=tuple(self.innerwear_tags),
                user_confirmed=True,
            )
        )
        if not self.default_outfit_id.get().strip():
            self.default_outfit_id.set(outfit_id)
        self._render_saved_outfits()
        next_number = len(self.confirmed_outfits) + 1
        existing_ids = {outfit.outfit_id for outfit in self.confirmed_outfits}
        while f"outfit-{next_number}" in existing_ids:
            next_number += 1
        self.outfit_id.set(f"outfit-{next_number}")
        self.outfit_name.set(f"Outfit {next_number}")
        self.outfit_tags.clear()
        self.innerwear_tags.clear()
        self._render_confirmed_tags()
        self.status.set(f"衣装「{outfit_name}」を追加しました。続けて別の衣装を分類できます。")

    # {
    #   責務: [_delete_outfit_profile: 選択された確認済みoutfitと画像割当を削除整合する]
    #   処理: [outfitを除去し, その衣装に紐付く画像をunknownへ戻してlistを更新する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _delete_outfit_profile(self) -> None:
        selected = self.saved_outfit_list.curselection()
        if not selected:
            self.status.set("削除する衣装候補を選択してください。")
            return
        removed_outfit = self.confirmed_outfits.pop(selected[0])
        cleared_assignments = 0
        for index, image in enumerate(self.reference_images):
            if image.outfit_id == removed_outfit.outfit_id:
                self.reference_images[index] = replace(
                    image,
                    outfit_assignment="unknown",
                    outfit_id=None,
                )
                cleared_assignments += 1
        self._render_saved_outfits()
        self._render_reference_images()
        if cleared_assignments:
            self.status.set(
                f"衣装「{removed_outfit.name}」を削除し、紐付く画像{cleared_assignments}件を未分類へ戻しました。"
            )

    # {
    #   責務: [_render_saved_outfits: 確認済みoutfit候補をUIへ表示する]
    #   処理: [衣装候補, 既定衣装selector, 参照画像の割当候補を更新する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _render_saved_outfits(self) -> None:
        self.saved_outfit_list.delete(0, "end")
        outfit_ids = tuple(outfit.outfit_id for outfit in self.confirmed_outfits)
        self.default_outfit_combo.configure(values=outfit_ids)
        if self.default_outfit_id.get() not in outfit_ids:
            self.default_outfit_id.set(outfit_ids[0] if outfit_ids else "")
        for outfit in self.confirmed_outfits:
            self.saved_outfit_list.insert(
                "end",
                f"{outfit.name} ({outfit.outfit_id})",
            )
        self._render_reference_image_assignment_choices()

    # {
    #   責務: [_render_reference_image_assignment_choices: 未分類/混在/登録衣装の割当候補を表示する]
    #   処理: [表示名とassignment kind/outfit IDの対応表を更新し, 画像選択状態を反映する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _render_reference_image_assignment_choices(self) -> None:
        choices = {
            "未分類 / 不明": ("unknown", None),
            "混在 / カスタム": ("mixed_custom", None),
        }
        for outfit in self.confirmed_outfits:
            choices[f"衣装: {outfit.name} ({outfit.outfit_id})"] = (
                "outfit",
                outfit.outfit_id,
            )
        self._reference_image_assignment_choices = choices
        self.reference_image_assignment_combo.configure(values=tuple(choices))
        self._select_reference_image()

    # {
    #   責務: [_select_reference_image: 選択画像の現在の衣装分類をcomboboxへ表示する]
    #   処理: [単一選択時に画像metadataと割当候補を照合して表示値を設定する]
    #   引数: [self: panel, event: Tk selection event]
    #   戻り値: []
    # }
    def _select_reference_image(self, _event: object = None) -> None:
        selected = self.reference_image_list.curselection()
        if len(selected) != 1:
            self.reference_image_assignment.set("")
            return
        image = self.reference_images[selected[0]]
        assignment = (image.outfit_assignment, image.outfit_id)
        label = next(
            (
                option
                for option, value in self._reference_image_assignment_choices.items()
                if value == assignment
            ),
            "未分類 / 不明",
        )
        self.reference_image_assignment.set(label)

    # {
    #   責務: [_assign_reference_image: 選択画像をunknown/mixed_custom/登録衣装へ割り当てる]
    #   処理: [単一選択画像のimmutable metadataを更新し, 一覧とstatusを反映する]
    #   引数: [self: panel]
    #   戻り値: []
    #   状態: [status: 選択不足や不正な割当を説明する]
    # }
    def _assign_reference_image(self) -> None:
        selected = self.reference_image_list.curselection()
        if len(selected) != 1:
            self.status.set("衣装を割り当てる参照画像を1件選択してください。")
            return
        label = self.reference_image_assignment.get()
        assignment = self._reference_image_assignment_choices.get(label)
        if assignment is None:
            self.status.set("画像の割当先を選択してください。")
            return
        index = selected[0]
        self.reference_images[index] = replace(
            self.reference_images[index],
            outfit_assignment=assignment[0],
            outfit_id=assignment[1],
        )
        self._render_reference_images()
        self.reference_image_list.selection_set(index)
        self.reference_image_assignment.set(label)
        self.status.set(f"参照画像の割当を「{label}」に更新しました。")

    # {
    #   責務: [_build_confirmation: UIの手動選択をregistration contractへ変換する]
    #   処理: [選択されたidentity, 複数衣装, 明示された既定衣装をconfirmationへ変換する]
    #   引数: [self: panel]
    #   戻り値: [CharacterTagIntakeConfirmation: 登録に使うmanual confirmation]
    #   エラー: [ValueError: outfit tag有りでoutfit情報が不正な場合]
    # }
    def _build_confirmation(self) -> CharacterTagIntakeConfirmation:
        """Convert the three visible tag categories into confirmed profile data."""
        outfits = list(self.confirmed_outfits)
        default_outfit_id = self.default_outfit_id.get().strip() or None
        if self.outfit_tags or self.innerwear_tags:
            outfit_id = self.outfit_id.get().strip()
            outfit_name = self.outfit_name.get().strip()
            if not outfit_id or not outfit_name:
                raise ValueError("outfit IDとoutfit名を入力してください。")
            current_outfit = CharacterOutfitProfile(
                outfit_id=outfit_id,
                name=outfit_name,
                garment_traits=tuple(self.outfit_tags),
                innerwear_traits=tuple(self.innerwear_tags),
                user_confirmed=True,
            )
            if any(outfit.outfit_id == outfit_id for outfit in outfits):
                raise ValueError(f"衣装ID「{outfit_id}」は重複しています。")
            outfits.append(current_outfit)
            if default_outfit_id is None:
                default_outfit_id = outfit_id
        return CharacterTagIntakeConfirmation(
            confirmed_identity_traits=tuple(self.identity_tags),
            outfit_profiles=tuple(outfits),
            default_outfit_id=default_outfit_id,
            reference_images=tuple(self.reference_images),
        )

    # {
    #   責務: [add_reference_images: file pickerで手動選択された画像を参照一覧へ追加する]
    #   処理: [画像をworkerでhashし, 同じ内容を除外して一覧へ描画する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def add_reference_images(self) -> None:
        selected_paths = filedialog.askopenfilenames(
            title="Characterの参照画像を選択",
            filetypes=(
                ("画像", "*.bmp *.gif *.jpeg *.jpg *.png *.webp"),
                ("すべてのファイル", "*.*"),
            ),
        )
        if not selected_paths:
            return
        self._start_task(
            "参照画像を読み込み中（コピーは行いません）...",
            lambda: tuple(
                self.messenger.load_character_reference_image(Path(path)) for path in selected_paths
            ),
            self._show_reference_images,
        )

    # {
    #   責務: [_show_reference_images: 読み込んだ参照画像を重複除外してUIへ反映する]
    #   処理: [内容IDが未登録の画像だけ保持し, 表示名とhash末尾を描画する]
    #   引数: [self: panel, result: 読み込んだreference image tuple]
    #   戻り値: []
    # }
    def _show_reference_images(self, result: object) -> None:
        images = tuple(result)
        known_ids = {image.image_id for image in self.reference_images}
        added = 0
        for image in images:
            if image.image_id not in known_ids:
                self.reference_images.append(image)
                known_ids.add(image.image_id)
                added += 1
        self._render_reference_images()
        self.status.set(
            f"参照画像を{added}件追加しました（重複を除外）。元画像はコピーしていません。"
        )

    # {
    #   責務: [remove_reference_images: 選択された参照画像を登録候補から外す]
    #   処理: [選択indexを逆順で除去して一覧を再描画する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def remove_reference_images(self) -> None:
        selected_indices = self.reference_image_list.curselection()
        if not selected_indices:
            self.status.set("削除する参照画像を選択してください。")
            return
        for index in reversed(selected_indices):
            del self.reference_images[index]
        self._render_reference_images()
        self.status.set(f"参照画像を{len(selected_indices)}件、登録候補から外しました。")

    # {
    #   責務: [_render_reference_images: 参照画像のpathとcontent IDを一覧表示する]
    #   処理: [Listboxと登録候補/元画像の存在/割当件数を現在のstateから再構築する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _render_reference_images(self) -> None:
        self.reference_image_list.delete(0, "end")
        for image in self.reference_images:
            path = Path(image.source_path)
            assignment_label = self._reference_image_assignment_label(image)
            self.reference_image_list.insert(
                "end",
                f"{path.name}  [{image.content_sha256[:12]}]  [{assignment_label}]  {image.source_path}",
            )
        self._select_reference_image()
        self.reference_image_statistics.set(
            format_reference_image_statistics(self.reference_images)
        )

    # {
    #   責務: [_reference_image_assignment_label: 画像割当metadataを一覧表示用の短い名前へ変換する]
    #   処理: [unknown/mixed/outfit stateから現在の表示名を返す]
    #   引数: [self: panel, image: 参照画像metadata]
    #   戻り値: [str: UI表示用の分類名]
    # }
    def _reference_image_assignment_label(self, image: CharacterReferenceImage) -> str:
        if image.outfit_assignment == "unknown":
            return "未分類 / 不明"
        if image.outfit_assignment == "mixed_custom":
            return "混在 / カスタム"
        outfit = next(
            (
                candidate
                for candidate in self.confirmed_outfits
                if candidate.outfit_id == image.outfit_id
            ),
            None,
        )
        if outfit is None:
            return f"衣装: {image.outfit_id}"
        return f"衣装: {outfit.name} ({outfit.outfit_id})"

    # {
    #   責務: [_show_registered_profile: 保存成功したprofile IDをUIへ表示する]
    #   処理: [registered profile name/idをstatusへ出す]
    #   引数: [self: panel, profile: 保存済みCharacterProfile]
    #   戻り値: []
    # }
    def _show_registered_profile(self, profile: CharacterProfile) -> None:
        """Keep the saved profile and begin exporting its wildcard bundle."""
        self._registered_profile = profile
        self._wildcard_retry_enabled = False
        self._start_task(
            "Characterを保存しました。wildcard bundleを書き出しています...",
            lambda: _write_wildcards_and_describe(
                self.messenger,
                profile,
                self.wildcard_root,
            ),
            self._show_wildcard_export_result,
        )

    # {
    #   責務: [_show_wildcard_export_result: wildcard出力結果と再試行可否をUIへ反映する]
    #   処理: [出力error時に保存済みprofileの再試行buttonを有効にする]
    #   引数: [self: panel, result: success flagと表示message]
    #   戻り値: []
    # }
    def _show_wildcard_export_result(self, result: tuple[bool, str]) -> None:
        """Show export status and enable retry only after a file-write failure."""
        succeeded, message = result
        self.status.set(message)
        self._wildcard_retry_enabled = not succeeded
        self._set_action_state("normal")

    # {
    #   責務: [retry_wildcard_export: 保存済みprofileのwildcard書き出しだけを再実行する]
    #   処理: [profileを再登録せず, exporterをworker threadへ依頼する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def retry_wildcard_export(self) -> None:
        """Retry export for the saved profile without registering it again."""
        profile = self._registered_profile
        if profile is None:
            self.status.set("再出力できる保存済みprofileがありません。")
            return
        self._wildcard_retry_enabled = False
        self._start_task(
            "保存済みprofileのwildcardを再出力中...",
            lambda: _write_wildcards_and_describe(
                self.messenger,
                profile,
                self.wildcard_root,
            ),
            self._show_wildcard_export_result,
        )

    # {
    #   責務: [save_lora_call_wildcard: 登録済みCharacterのLoRA呼び出し候補を保存する]
    #   処理: [候補欄と設定済みwildcard rootをmessengerへ渡し, 結果をstatusへ表示する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def save_lora_call_wildcard(self) -> None:
        """Save weighted local LoRA calls for the last successfully registered profile."""
        profile = self._registered_profile
        if profile is None:
            self.status.set("先にCharacterを登録してください。")
            return
        content = self.view.lora_call_text.get("1.0", "end-1c")
        if not content.strip():
            self.status.set("LoRA候補を1行以上入力してください。")
            return
        try:
            written = self.messenger.write_character_lora_call_wildcard(
                profile.character_id,
                content,
                self.wildcard_root,
            )
        except (OSError, ValueError) as error:
            self.status.set(f"LoRA候補を保存できません: {error}")
            return
        self.status.set(f"{profile.display_name}のLoRA候補wildcardを保存しました: {written[0]}")

    # {
    #   責務: [_start_task: blocking API/workをworker threadで実行する]
    #   処理: [buttonをdisableし, 結果Queueをpollする]
    #   引数: [self: panel, label: 表示中status, operation: worker operation, on_success: UI callback]
    #   戻り値: []
    # }
    def _start_task(
        self,
        label: str,
        operation: Callable[[], object],
        on_success: Callable[[object], None],
    ) -> None:
        if self._task_pending:
            return
        self._task_pending = True
        self._set_action_state("disabled")
        self.status.set(label)
        worker = threading.Thread(
            target=self._run_task,
            args=(operation,),
            daemon=True,
            name="character-registry-ui-worker",
        )
        worker.start()
        self.after(60, lambda: self._poll_task(on_success))

    # {
    #   責務: [_run_task: worker threadでoperationを実行して結果をQueueへ送る]
    #   処理: [例外を含めてresult tupleをtask queueへputする]
    #   引数: [self: panel, operation: worker callable]
    #   戻り値: []
    # }
    def _run_task(self, operation: Callable[[], object]) -> None:
        try:
            self._task_results.put((True, operation()))
        except Exception as error:
            self._task_results.put((False, error))

    # {
    #   責務: [_poll_task: UI threadでworker resultを受け取り画面へ反映する]
    #   処理: [結果が無ければafterで再確認し, 完了時にbuttonsを戻す]
    #   引数: [self: panel, on_success: 成功結果を表示するcallback]
    #   戻り値: []
    # }
    def _poll_task(self, on_success: Callable[[object], None]) -> None:
        try:
            succeeded, value = self._task_results.get_nowait()
        except Empty:
            self.after(60, lambda: self._poll_task(on_success))
            return
        self._task_pending = False
        self._set_action_state("normal")
        if succeeded:
            on_success(value)
        else:
            self.status.set(f"処理エラー: {type(value).__name__}: {value}")

    # {
    #   責務: [_set_action_state: worker中に操作するbutton群を有効/無効化する]
    #   処理: [search, preview, register, retry, image選択buttonをworker状態に合わせて更新する]
    #   引数: [self: panel, state: Tk button state]
    #   戻り値: []
    # }
    def _set_action_state(self, state: str) -> None:
        """Update action availability while preserving the wildcard retry condition."""
        for button in (
            self.search_button,
            self.next_page_button,
            self.preview_button,
            self.register_button,
            self.add_reference_images_button,
            self.remove_reference_images_button,
        ):
            button.configure(state=state)
        retry_state = (
            "normal" if state != "disabled" and self._wildcard_retry_enabled else "disabled"
        )
        self.wildcard_retry_button.configure(state=retry_state)
