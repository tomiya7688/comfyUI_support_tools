import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk

from ..backend.ai_origin_clustering import (
    ImageOriginResult,
    classify_images,
    copy_clusters,
    discover_images,
    write_manifest,
)
from ..backend.ai_origin_detector import AnimeAIDetector
from ..widgets.labeled_path_row import LabeledPathRow
from ..widgets.log_box import LogBox


# {
# 責務: [AIImageClusterTab: AI画像の分類と確認UIを提供する]
# フィールド: [状態: AI画像の分類と確認UIを提供する]
# }
class AIImageClusterTab(ttk.Frame):
    MODEL_ID = "saltacc/anime-ai-detect"

    # {
    # 責務: [__init__: 依存と設定値を初期化する]
    # 処理: [1: 依存と設定値を初期化する]
    # 引数: [self, master]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.model_id = tk.StringVar(value=self.MODEL_ID)
        self.device = tk.StringVar(value="auto")
        self.low_threshold = tk.StringVar(value="0.1")
        self.high_threshold = tk.StringVar(value="0.9")
        self.override_cluster = tk.StringVar(value="uncertain")
        self.recursive = tk.BooleanVar(value=True)
        self.results: list[ImageOriginResult] = []
        self._source_root: Path | None = None
        self._output_root: Path | None = None
        self.busy = False
        self._build()

    # {
    # 責務: [_build: 設定と結果表示UIを構築する]
    # 処理: [1: 設定と結果表示UIを構築する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _build(self):
        paths = ttk.LabelFrame(self, text="入出力", padding=8)
        paths.pack(fill="x")
        LabeledPathRow(paths, "画像フォルダー", self.input_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(paths, "クラスタ出力先", self.output_dir, mode="dir").pack(fill="x", pady=3)

        settings = ttk.LabelFrame(self, text="OSS判定器", padding=8)
        settings.pack(fill="x", pady=6)
        ttk.Label(settings, text="モデルID").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(settings, textvariable=self.model_id, width=45, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Label(settings, text="デバイス").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Combobox(
            settings,
            textvariable=self.device,
            values=("auto", "cpu", "cuda"),
            state="readonly",
            width=8,
        ).grid(row=0, column=3, padx=4)
        ttk.Label(settings, text="非AI上限").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(settings, textvariable=self.low_threshold, width=8).grid(
            row=1, column=1, sticky="w", padx=4
        )
        ttk.Label(settings, text="AI下限").grid(row=1, column=2, sticky="w", padx=4)
        ttk.Entry(settings, textvariable=self.high_threshold, width=8).grid(
            row=1, column=3, sticky="w", padx=4
        )
        settings.columnconfigure(1, weight=1)
        ttk.Checkbutton(settings, text="サブフォルダーを再帰処理", variable=self.recursive).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=4, pady=3
        )

        ttk.Label(
            self,
            text="metadata (Pixiv/生成情報)を優先し、判定器の中間スコアは「要確認」に分けます。画像はローカル処理です。",
            wraplength=900,
        ).pack(anchor="w", pady=4)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=4)
        ttk.Button(buttons, text="解析してプレビュー", command=self.start_analysis).pack(
            side="left", padx=4
        )
        self.save_button = ttk.Button(
            buttons, text="結果を保存", command=self.save_results, state="disabled"
        )
        self.save_button.pack(side="left", padx=4)
        self.copy_button = ttk.Button(
            buttons, text="クラスタへコピー", command=self.copy_results, state="disabled"
        )
        self.copy_button.pack(side="left", padx=4)

        columns = ("cluster", "confidence", "evidence", "reason", "path")
        self.result_table = ttk.Treeview(self, columns=columns, show="headings", height=12)
        for key, label, width in (
            ("cluster", "クラスタ", 115),
            ("confidence", "AIスコア", 80),
            ("evidence", "根拠", 180),
            ("reason", "判定理由", 210),
            ("path", "画像", 500),
        ):
            self.result_table.heading(key, text=label)
            self.result_table.column(key, width=width, anchor="w")
        self.result_table.pack(fill="both", expand=True, pady=4)
        review = ttk.Frame(self)
        review.pack(fill="x", pady=3)
        ttk.Label(review, text="選択画像の手動修正").pack(side="left", padx=4)
        ttk.Combobox(
            review,
            textvariable=self.override_cluster,
            values=("ai_generated", "non_ai", "uncertain"),
            state="readonly",
            width=16,
        ).pack(side="left", padx=4)
        self.override_button = ttk.Button(
            review, text="選択行へ適用", command=self.override_selected, state="disabled"
        )
        self.override_button.pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    # 責務: [start_analysis: 入力を検証して解析を開始する]
    # 処理: [1: 入力を検証して解析を開始する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def start_analysis(self):
        if self.busy:
            return
        try:
            if not self.input_dir.get().strip():
                raise ValueError("画像フォルダーを指定してください")
            if not self.output_dir.get().strip():
                raise ValueError("クラスタ出力先を指定してください")
            source = Path(self.input_dir.get()).expanduser().resolve(strict=True)
            output = Path(self.output_dir.get()).expanduser().resolve()
            low, high = float(self.low_threshold.get()), float(self.high_threshold.get())
            if not source.is_dir():
                raise ValueError("入力元はフォルダーを指定してください")
            if output == source or source in output.parents:
                raise ValueError("出力先は入力フォルダーの外に指定してください")
            if not 0 <= low < high <= 1:
                raise ValueError("しきい値は 0 <= 非AI上限 < AI下限 <= 1 にしてください")
        except (OSError, ValueError) as error:
            self.logbox.log(f"入力エラー: {error}")
            return

        self.busy = True
        self.results = []
        self._source_root = None
        self._output_root = None
        self._set_action_states(False)
        self.result_table.delete(*self.result_table.get_children())
        threading.Thread(
            target=self._classify_worker,
            args=(
                source,
                output,
                low,
                high,
                self.model_id.get(),
                self.device.get(),
                self.recursive.get(),
            ),
            daemon=True,
        ).start()

    # {
    # 責務: [_classify_worker: 画像分類をバックグラウンド実行する]
    # 処理: [1: 画像分類をバックグラウンド実行する]
    # 引数: [self, source, output, low, high, model_id, device, recursive]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _classify_worker(self, source, output, low, high, model_id, device, recursive):
        try:
            images = discover_images(source, recursive, output)
            if not images:
                raise ValueError("指定フォルダーに対応画像がありません")
            detector = AnimeAIDetector(model_id, device)
            results = classify_images(
                images,
                detector,
                low,
                high,
                progress=lambda current, total, path: self.after(
                    0, self.logbox.log, f"判定中 {current}/{total}: {path.name}"
                ),
            )
            self.after(0, self._show_results, results, source, output)
        except Exception as error:
            self.after(0, self.logbox.log, f"判定エラー: {type(error).__name__}: {error}")
            self.after(0, self._set_idle)

    # {
    # 責務: [_show_results: 分類結果を一覧へ表示する]
    # 処理: [1: 分類結果を一覧へ表示する]
    # 引数: [self, results, source, output]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _show_results(self, results, source, output):
        self.results = results
        self._source_root = source
        self._output_root = output
        for index, result in enumerate(results):
            confidence = "" if result.confidence is None else f"{result.confidence:.3f}"
            self.result_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    result.cluster,
                    confidence,
                    ", ".join(result.evidence),
                    result.reason,
                    str(result.source_path),
                ),
            )
        counts = {
            label: sum(result.cluster == label for result in results)
            for label in ("ai_generated", "non_ai", "uncertain")
        }
        self.logbox.log(
            f"解析完了: AI {counts['ai_generated']} / 非AI {counts['non_ai']} / 要確認 {counts['uncertain']}"
        )
        classifier_errors = [result for result in results if "classifier_error" in result.evidence]
        if classifier_errors:
            self.logbox.log(
                f"OSS判定器エラー {len(classifier_errors)}件: {classifier_errors[0].reason}"
            )
        self.busy = False
        self._set_action_states(bool(results))

    # {
    # 責務: [_set_idle: 実行中状態を解除する]
    # 処理: [1: 実行中状態を解除する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _set_idle(self):
        self.busy = False
        self._set_action_states(bool(self.results))

    # {
    # 責務: [_set_action_states: 結果操作を状態に応じて有効化する]
    # 処理: [1: 保存・コピー・手動修正ボタンを切り替える]
    # 引数: [self, enabled: 操作可能ならTrue]
    # 戻り値: []
    # }
    def _set_action_states(self, enabled):
        state = "normal" if enabled and not self.busy else "disabled"
        for button in (self.save_button, self.copy_button, self.override_button):
            button.configure(state=state)

    # {
    # 責務: [save_results: 分類結果をmanifestに保存する]
    # 処理: [1: 分類結果をmanifestに保存する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def save_results(self):
        if not self.results:
            self.logbox.log("先に画像を解析してください")
            return
        if self.busy:
            return
        try:
            manifest = write_manifest(self.results, self._output_root / "ai_origin_manifest.json")
            self.logbox.log(f"結果を保存しました: {manifest}")
        except OSError as error:
            self.logbox.log(f"保存エラー: {error}")

    # {
    # 責務: [override_selected: 選択行の分類を手動修正する]
    # 処理: [1: 選択行の分類を手動修正する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def override_selected(self):
        if self.busy:
            return
        selection = self.result_table.selection()
        if not selection:
            self.logbox.log("手動修正する画像を選択してください")
            return
        index = int(selection[0])
        result = self.results[index]
        self.results[index] = replace(
            result,
            cluster=self.override_cluster.get(),
            evidence=(*result.evidence, "user_override"),
            reason="user_override",
            user_override=True,
        )
        updated = self.results[index]
        confidence = "" if updated.confidence is None else f"{updated.confidence:.3f}"
        self.result_table.item(
            selection[0],
            values=(
                updated.cluster,
                confidence,
                ", ".join(updated.evidence),
                updated.reason,
                str(updated.source_path),
            ),
        )
        self.logbox.log(f"分類を修正しました: {updated.source_path.name} → {updated.cluster}")

    # {
    # 責務: [copy_results: 確認済み画像をクラスタ先へコピーする]
    # 処理: [1: 確認済み画像をクラスタ先へコピーする]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def copy_results(self):
        if not self.results:
            self.logbox.log("先に画像を解析してください")
            return
        if self.busy:
            return
        if not messagebox.askyesno(
            "クラスタへコピー",
            f"画像を次のフォルダーへコピーします。元画像は保持されます。\n\n{self._output_root}",
            parent=self,
        ):
            return
        if self.busy:
            return
        self.busy = True
        self._set_action_states(False)
        results_snapshot = tuple(self.results)
        source_root = self._source_root
        output_root = self._output_root
        threading.Thread(
            target=self._copy_worker,
            args=(results_snapshot, source_root, output_root),
            daemon=True,
        ).start()

    # {
    # 責務: [_copy_worker: クラスタコピーをバックグラウンド実行する]
    # 処理: [1: クラスタコピーをバックグラウンド実行する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _copy_worker(self, results, source_root, output_root):
        try:
            count = copy_clusters(results, source_root, output_root)
            manifest = write_manifest(results, output_root / "ai_origin_manifest.json")
            self.after(0, self.logbox.log, f"クラスタコピー完了: {count}枚。結果: {manifest}")
        except (OSError, ValueError) as error:
            self.after(0, self.logbox.log, f"コピーエラー: {error}")
        finally:
            self.after(0, self._set_idle)
