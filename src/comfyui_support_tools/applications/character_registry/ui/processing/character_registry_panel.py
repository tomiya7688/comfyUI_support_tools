from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, simpledialog, ttk

from src.comfyui_support_tools.applications.character_registry.ui.messenger.character_registry_ui_messenger import (
    CharacterRegistryUiMessenger,
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


# {
#   責務: [CharacterRegistryPanel: Civitai/local caption intakeの検索,分類確認,登録UIを表示する]
#   フィールド: [UI widgets, selected candidates, preview, async request queue]
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
    ) -> None:
        super().__init__(master, padding=12)
        self.messenger = messenger
        self.settings_store = settings_store
        self.candidates: tuple[CivitaiLoraCandidate, ...] = ()
        self.preview: CharacterTagIntakePreview | None = None
        self.identity_tags: list[str] = []
        self.outfit_tags: list[str] = []
        self._task_results: Queue[tuple[bool, object]] = Queue()
        self._task_pending = False
        self.status = tk.StringVar(value="caption folderを選び、previewを作成してください。")
        try:
            settings = self.settings_store.load()
        except ValueError as error:
            settings = {"dataset_root": "", "profile_directory": ""}
            self.status.set(f"保存済みpath設定を読み込めません: {error}")
        self.character_id = tk.StringVar(value=create_character_id())
        self.display_name = tk.StringVar()
        self.aliases = tk.StringVar()
        self.dataset_root = tk.StringVar(value=settings["dataset_root"])
        self.profile_directory = tk.StringVar(value=settings["profile_directory"])
        self.civitai_query = tk.StringVar()
        self.outfit_id = tk.StringVar(value="default")
        self.outfit_name = tk.StringVar(value="Default Outfit")
        variables = {
            "dataset_root": self.dataset_root,
            "profile_directory": self.profile_directory,
            "character_id": self.character_id,
            "display_name": self.display_name,
            "aliases": self.aliases,
            "civitai_query": self.civitai_query,
            "outfit_id": self.outfit_id,
            "outfit_name": self.outfit_name,
            "status": self.status,
        }
        actions = {
            "choose_dataset": self._choose_dataset,
            "choose_profile_directory": self._choose_profile_directory,
            "regenerate_id": self._regenerate_character_id,
            "search_civitai": self.search_civitai,
            "preview_intake": self.preview_intake,
            "add_identity": self._add_identity,
            "add_outfit": self._add_outfit,
            "remove_identity": self._remove_identity,
            "remove_outfit": self._remove_outfit,
            "add_custom_tag": self._add_custom_tag,
            "register_profile": self.register_profile,
        }
        self.view = CharacterRegistryPanelView(self, variables, actions)
        self.view.pack(fill="both", expand=True)
        self.candidate_list = self.view.candidate_list
        self.suggestion_list = self.view.suggestion_list
        self.identity_list = self.view.identity_list
        self.outfit_list = self.view.outfit_list
        self.search_button = self.view.search_button
        self.preview_button = self.view.preview_button
        self.register_button = self.view.register_button

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
    def _save_paths(self) -> None:
        try:
            self.settings_store.save(self.dataset_root.get(), self.profile_directory.get())
            self.status.set("path設定を保存しました。")
        except (OSError, ValueError) as error:
            self.status.set(f"path設定の保存に失敗: {error}")

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
        query = self.civitai_query.get().strip()
        if not query:
            self.status.set("Civitaiの検索語を入力してください。")
            return
        self._start_task(
            "Civitai候補を検索中...",
            lambda: self.messenger.search_civitai_loras(query),
            self._show_candidates,
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
    ) -> None:
        candidates, _cursor = result
        self.candidates = tuple(candidates)
        self.candidate_list.delete(0, "end")
        for candidate in self.candidates:
            creator = candidate.creator or "作者不明"
            self.candidate_list.insert(
                "end",
                f"{candidate.model_name} / {candidate.version_name} — {creator} / {candidate.base_model}",
            )
        self.status.set(f"Civitai候補: {len(self.candidates)}件。選択は任意です。")

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
    #   処理: [formをvalidateし, selected candidateを指定して非同期previewする]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def preview_intake(self) -> None:
        try:
            request = self._build_request()
        except ValueError as error:
            self.status.set(str(error))
            return
        candidate = self._selected_candidate()
        self._start_task(
            "captionとtag分類を確認中...",
            lambda: self.messenger.preview_character_intake(request, candidate),
            self._show_preview,
        )

    # {
    #   責務: [_build_request: form inputからCharacterTagIntakeRequestを作る]
    #   処理: [ID/name/dataset directoryを検証し, aliasesを区切ってrequestにする]
    #   引数: [self: panel]
    #   戻り値: [CharacterTagIntakeRequest: API request]
    #   エラー: [ValueError: 必須inputが空またはdatasetが存在しない場合]
    # }
    def _build_request(self) -> CharacterTagIntakeRequest:
        dataset_root = Path(self.dataset_root.get().strip()).expanduser()
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
        self.preview = preview
        self.identity_tags.clear()
        self.outfit_tags.clear()
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
    #   責務: [_render_confirmed_tags: identity/outfitの確認済み候補をlistboxに反映する]
    #   処理: [2 listsをtag順のまま再描画する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _render_confirmed_tags(self) -> None:
        for listing, tags in (
            (self.identity_list, self.identity_tags),
            (self.outfit_list, self.outfit_tags),
        ):
            listing.delete(0, "end")
            for tag in tags:
                listing.insert("end", tag)

    # {
    #   責務: [_add_custom_tag: previewに無い手動修正tagをidentity/outfitへ追加する]
    #   処理: [userのcategoryとcustom textを確認してtag listへ追加する]
    #   引数: [self: panel]
    #   戻り値: []
    # }
    def _add_custom_tag(self) -> None:
        value = simpledialog.askstring("Custom tag", "追加するtagを入力してください。", parent=self)
        if not value:
            return
        category = simpledialog.askstring(
            "分類先", "identity または outfit を入力してください。", parent=self
        )
        destination = {"identity": self.identity_tags, "outfit": self.outfit_tags}.get(
            (category or "").strip().lower()
        )
        if destination is None:
            self.status.set("分類先にはidentityまたはoutfitを指定してください。")
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
        if self.preview is None:
            self.status.set("先にtag previewを作成してください。")
            return
        if not self.identity_tags:
            self.status.set("登録するidentity tagを選択してください。")
            return
        profile_directory = Path(self.profile_directory.get().strip()).expanduser()
        if not profile_directory.is_absolute():
            self.status.set("profile folderを選択してください。")
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
    #   責務: [_build_confirmation: UIの手動選択をregistration contractへ変換する]
    #   処理: [選択されたidentity/outfitをuser_confirmed profileへ変換する]
    #   引数: [self: panel]
    #   戻り値: [CharacterTagIntakeConfirmation: 登録に使うmanual confirmation]
    #   エラー: [ValueError: outfit tag有りでoutfit情報が不正な場合]
    # }
    def _build_confirmation(self) -> CharacterTagIntakeConfirmation:
        outfits: tuple[CharacterOutfitProfile, ...] = ()
        default_outfit_id: str | None = None
        if self.outfit_tags:
            outfit_id = self.outfit_id.get().strip()
            outfit_name = self.outfit_name.get().strip()
            if not outfit_id or not outfit_name:
                raise ValueError("outfit IDとoutfit名を入力してください。")
            outfits = (
                CharacterOutfitProfile(
                    outfit_id=outfit_id,
                    name=outfit_name,
                    garment_traits=tuple(self.outfit_tags),
                    user_confirmed=True,
                ),
            )
            default_outfit_id = outfit_id
        return CharacterTagIntakeConfirmation(
            confirmed_identity_traits=tuple(self.identity_tags),
            outfit_profiles=outfits,
            default_outfit_id=default_outfit_id,
        )

    # {
    #   責務: [_show_registered_profile: 保存成功したprofile IDをUIへ表示する]
    #   処理: [registered profile name/idをstatusへ出す]
    #   引数: [self: panel, profile: 保存済みCharacterProfile]
    #   戻り値: []
    # }
    def _show_registered_profile(self, profile: CharacterProfile) -> None:
        self.status.set(f"登録しました: {profile.display_name} ({profile.character_id})")

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
    #   処理: [Civitai search, preview, register buttonへ同じstateを設定する]
    #   引数: [self: panel, state: Tk button state]
    #   戻り値: []
    # }
    def _set_action_state(self, state: str) -> None:
        for button in (self.search_button, self.preview_button, self.register_button):
            button.configure(state=state)
