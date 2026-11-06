from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk


# {
#   責務: [CharacterRegistryPanelView: Character Registry intake controllerのTk widgetsを構築する]
#   フィールド: [form variables, candidate/review listboxes, action buttons]
# }
class CharacterRegistryPanelView(ttk.Frame):
    # {
    #   責務: [__init__: UI状態変数と操作callbackを受け取り画面を構成する]
    #   処理: [明示されたvariables/actionsを保持し, intake画面をbuildする]
    #   引数: [self: view, master: Tk parent, variables: StringVar map, actions: UI action callback map]
    #   戻り値: []
    # }
    def __init__(
        self,
        master: tk.Misc,
        variables: Mapping[str, tk.StringVar],
        actions: Mapping[str, Callable[[], None]],
    ) -> None:
        super().__init__(master, padding=12)
        self.variables = variables
        self.actions = actions
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build()

    # {
    #   責務: [_build: intakeフォームの各view領域を配置する]
    #   処理: [path, character, Civitai, tag review, registerの5領域をbuildする]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build(self) -> None:
        self._build_paths()
        self._build_character_fields()
        self._build_civitai_search()
        self._build_review_columns()
        self._build_lora_call_editor()
        self._build_actions()

    # {
    #   責務: [_build_lora_call_editor: Character用の重み付きLoRA呼び出し候補欄を配置する]
    #   処理: [複数行入力欄と保存buttonを表示する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_lora_call_editor(self) -> None:
        """Build a multiline editor for weighted local LoRA-call choices."""
        editor = ttk.LabelFrame(self, text="Character LoRA候補（ローカル名を指定）", padding=8)
        editor.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        editor.columnconfigure(0, weight=1)
        ttk.Label(
            editor,
            text="登録後に保存できます。例: @weight=3::<lora:local_model_a:0.8> / <lora:local_model_b:0.7>",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self.lora_call_text = tk.Text(editor, height=4, wrap="none", undo=True)
        self.lora_call_text.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        scrollbar = ttk.Scrollbar(editor, orient="vertical", command=self.lora_call_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.lora_call_text.configure(yscrollcommand=scrollbar.set)
        ttk.Button(
            editor,
            text="LoRA候補を保存",
            command=self.actions["save_lora_call_wildcard"],
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    # {
    #   責務: [_build_paths: datasetとprofile保存pathの入力欄を配置する]
    #   処理: [directory fieldとbrowse buttonを2行で表示する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_paths(self) -> None:
        paths = ttk.LabelFrame(self, text="入力・保存先", padding=8)
        paths.grid(row=0, column=0, sticky="ew")
        paths.columnconfigure(1, weight=1)
        self._add_path_row(
            paths,
            0,
            "caption folder",
            self.variables["dataset_root"],
            self.actions["choose_dataset"],
        )
        self._add_path_row(
            paths,
            1,
            "profile folder",
            self.variables["profile_directory"],
            self.actions["choose_profile_directory"],
        )

    # {
    #   責務: [_add_path_row: directory path用のentryとbrowse buttonを配置する]
    #   処理: [label, entry, browse buttonを同じrowへ並べる]
    #   引数: [parent: row parent, row: row number, label: field label, variable: path StringVar, command: browse callback]
    #   戻り値: []
    # }
    @staticmethod
    def _add_path_row(
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=label, width=15).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)
        ttk.Button(parent, text="参照...", command=command).grid(
            row=row, column=2, padx=(6, 0), pady=2
        )

    # {
    #   責務: [_build_character_fields: stable ID, display name, aliases入力欄を配置する]
    #   処理: [3つのfieldとID再生成buttonを表示する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_character_fields(self) -> None:
        details = ttk.LabelFrame(self, text="Character", padding=8)
        details.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        details.columnconfigure(1, weight=1)
        fields = (
            (0, "stable ID", "character_id"),
            (1, "表示名", "display_name"),
            (2, "別名（comma区切り）", "aliases"),
        )
        for row, label, variable_name in fields:
            ttk.Label(details, text=label, width=20).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(details, textvariable=self.variables[variable_name]).grid(
                row=row, column=1, sticky="ew", pady=2
            )
        ttk.Button(details, text="IDを再生成", command=self.actions["regenerate_id"]).grid(
            row=0, column=2, padx=(6, 0)
        )

    # {
    #   責務: [_build_civitai_search: Civitai queryとversion候補欄を配置する]
    #   処理: [検索field, button,候補listboxとmetadata説明を配置する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_civitai_search(self) -> None:
        """Build query, metadata-only result list, and next-page control."""
        search = ttk.LabelFrame(self, text="Civitai LoRA候補（metadata only）", padding=8)
        search.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        search.columnconfigure(0, weight=1)
        row = ttk.Frame(search)
        row.grid(row=0, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self.variables["civitai_query"]).grid(
            row=0, column=0, sticky="ew"
        )
        self.search_button = ttk.Button(row, text="検索", command=self.actions["search_civitai"])
        self.search_button.grid(row=0, column=1, padx=(6, 0))
        self.next_page_button = ttk.Button(
            row,
            text="次の候補",
            command=self.actions["next_civitai_page"],
            state="disabled",
        )
        self.next_page_button.grid(row=0, column=2, padx=(6, 0))
        self.candidate_list = tk.Listbox(search, height=3, exportselection=False)
        self.candidate_list.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(
            search,
            text="重み・画像は取得しません。selected versionのtrainedWordsだけをpreviewに使います。",
            wraplength=850,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    # {
    #   責務: [_build_review_columns: 候補と手動確認済みtagの4列を配置する]
    #   処理: [候補, identity, outfit, hidden innerwear listboxと操作buttonを表示する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_review_columns(self) -> None:
        """Build candidate, identity, outfit, and hidden-innerwear lists."""
        review = ttk.LabelFrame(self, text="タグ分類の確認", padding=8)
        review.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        for column in range(4):
            review.columnconfigure(column, weight=1)
        self.suggestion_list = self._add_listbox(review, 0, "候補（未確認）")
        self.identity_list = self._add_listbox(review, 1, "identity（登録対象）")
        self.outfit_list = self._add_listbox(review, 2, "outfit（通常prompt）")
        self.innerwear_list = self._add_listbox(review, 3, "innerwear（通常promptには出さない）")
        controls = ttk.Frame(review)
        controls.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        self.preview_button = ttk.Button(
            controls,
            text="タグpreviewを作成",
            command=self.actions["preview_intake"],
        )
        self.preview_button.pack(side="left")
        button_actions = (
            ("選択 → identity", "add_identity"),
            ("選択 → outfit", "add_outfit"),
            ("選択 → innerwear", "add_innerwear"),
            ("identityから削除", "remove_identity"),
            ("outfitから削除", "remove_outfit"),
            ("innerwearから削除", "remove_innerwear"),
            ("custom tag追加", "add_custom_tag"),
        )
        for label, action_name in button_actions:
            ttk.Button(controls, text=label, command=self.actions[action_name]).pack(
                side="left", padx=4
            )

    # {
    #   責務: [_add_listbox: headingとscrollbarつきListboxを1列へ配置する]
    #   処理: [select modeのListboxと縦scrollbarを接続する]
    #   引数: [parent: review frame, column: column number, title: list heading]
    #   戻り値: [tk.Listbox: 表示するlistbox]
    # }
    @staticmethod
    def _add_listbox(parent: ttk.LabelFrame, column: int, title: str) -> tk.Listbox:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="nsew", padx=3)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title).grid(row=0, column=0, columnspan=2, sticky="w")
        listing = tk.Listbox(frame, height=8, selectmode="extended", exportselection=False)
        listing.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=listing.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        listing.configure(yscrollcommand=scrollbar.set)
        return listing

    # {
    #   責務: [_build_actions: outfit fields,登録button,statusを配置する]
    #   処理: [default outfit設定とregistration状態を表示する]
    #   引数: [self: view]
    #   戻り値: []
    # }
    def _build_actions(self) -> None:
        """Build outfit details, registration, export retry, and status controls."""
        actions = ttk.LabelFrame(self, text="登録", padding=8)
        actions.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(actions, text="outfit ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(actions, textvariable=self.variables["outfit_id"], width=18).grid(
            row=0, column=1, padx=4
        )
        ttk.Label(actions, text="outfit名").grid(row=0, column=2, sticky="w")
        ttk.Entry(actions, textvariable=self.variables["outfit_name"], width=24).grid(
            row=0, column=3, padx=4
        )
        self.register_button = ttk.Button(
            actions,
            text="確認内容でCharacterを登録",
            command=self.actions["register_profile"],
        )
        self.register_button.grid(row=0, column=4, padx=(8, 4))
        self.wildcard_retry_button = ttk.Button(
            actions,
            text="wildcard出力を再試行",
            command=self.actions["retry_wildcard_export"],
            state="disabled",
        )
        self.wildcard_retry_button.grid(row=0, column=5, padx=(4, 4))
        ttk.Label(actions, textvariable=self.variables["status"]).grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(6, 0)
        )
