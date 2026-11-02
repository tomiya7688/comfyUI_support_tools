"""Explicit output choices for caption/TXT/metadata migration."""

import tkinter as tk
from tkinter import filedialog, ttk

from comfyui_support_tools.shared.contracts.inspector_contracts import ExportSettings


# {
# 責務: [ExportDialog: 明示的なcaption/metadata/batch TXT出力先とoverwrite optionを収集する]
# フィールド: [on_export callback, log callback, output/settings Tk variables]
# }
class ExportDialog(tk.Toplevel):
    # {
    #   責務: [__init__: export choicesを表示するtransient dialogを構築する]
    #   処理: [sidecar/batch/style/overwrite controlsを作り、submit時にon_exportへ渡す]
    #   引数: [self: dialog, parent: parent widget, on_export: settings submit callback, log: error callback]
    #   戻り値: [なし]
    #   副作用: [Tk widgetsとvariablesを生成する]
    # }
    def __init__(self, parent, on_export, log):
        super().__init__(parent)
        self.on_export = on_export
        self.log = log
        self.title("Analysis結果を書き出す")
        self.transient(parent.winfo_toplevel())
        self.geometry("620x330")
        self.minsize(520, 330)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.caption = tk.BooleanVar(self, value=True)
        self.metadata = tk.BooleanVar(self, value=True)
        self.batch_enabled = tk.BooleanVar(self, value=False)
        self.batch_path = tk.StringVar(self)
        self.include_style = tk.BooleanVar(self, value=False)
        self.overwrite = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(
            body,
            text="画像と同じ場所へ caption sidecar (.txt)",
            variable=self.caption,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="画像と同じ場所へ構造化 metadata (.画像拡張子.kadoka.json)",
            variable=self.metadata,
        ).pack(anchor="w", pady=3)
        row = ttk.Frame(body)
        row.pack(fill="x", pady=3)
        ttk.Checkbutton(row, text="Batch TXT", variable=self.batch_enabled).pack(side="left")
        ttk.Entry(row, textvariable=self.batch_path).pack(
            side="left", fill="x", expand=True, padx=5
        )
        ttk.Button(row, text="選択", command=self._choose_batch).pack(side="left")
        ttk.Checkbutton(
            body,
            text="caption生成時にStyle tagsも連結する",
            variable=self.include_style,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            body,
            text="既存sidecar/metadata/batch TXTの上書きを許可",
            variable=self.overwrite,
        ).pack(anchor="w", pady=3)
        ttk.Label(
            body,
            text=(
                "captionはimage-to-text captionがあれば優先し、なければcontent/character/copyright tagsから生成します。\n"
                "元画像は変更しません。既存ファイルは上書きONにしない限り失敗します。"
            ),
            wraplength=570,
        ).pack(anchor="w", pady=8)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="書き出す", command=self._submit).pack(side="left")
        ttk.Button(buttons, text="閉じる", command=self.destroy).pack(side="right")

    # {
    #   責務: [_choose_batch: Save As chooserでbatch TXT pathを選択する]
    #   処理: [path選択成功時だけbatch出力を有効化しentry valueを更新する]
    #   引数: [self: dialog]
    #   戻り値: [なし]
    #   副作用: [native save dialogを開きTk variablesを変更する]
    # }
    def _choose_batch(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Batch TXT出力",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if path:
            self.batch_enabled.set(True)
            self.batch_path.set(path)

    # {
    #   責務: [_submit: UI selectionsをExportSettingsへ変換してexport callbackを呼ぶ]
    #   処理: [batch無効時pathを空にし、callbackが成功を返した場合だけdialogを閉じる]
    #   引数: [self: dialog]
    #   戻り値: [なし]
    #   エラー: [ValueError/OSErrorをlog callbackへ渡してdialogを維持する]
    #   副作用: [export callbackを実行し成功時dialogをdestroyする]
    # }
    def _submit(self):
        settings = ExportSettings(
            caption_sidecar=self.caption.get(),
            metadata_sidecar=self.metadata.get(),
            batch_txt_path=self.batch_path.get().strip() if self.batch_enabled.get() else "",
            include_style_in_caption=self.include_style.get(),
            overwrite=self.overwrite.get(),
        )
        try:
            if self.on_export(settings):
                self.destroy()
        except (ValueError, OSError) as exc:
            self.log(str(exc))
