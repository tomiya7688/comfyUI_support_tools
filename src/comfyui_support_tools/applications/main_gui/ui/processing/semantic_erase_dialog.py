"""Manual-mask review dialog for non-destructive Semantic Erase."""

import os
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from comfyui_support_tools.shared.semantic_erase.contracts import (
    MAX_IMAGE_PIXELS,
    EraseMode,
    EraseRequest,
    FillPolicy,
    MatchPolicy,
    RLEMask,
    SemanticEraseTarget,
)
from comfyui_support_tools.shared.semantic_erase.history import EraseHistoryStore
from comfyui_support_tools.shared.semantic_erase.service import SemanticEraseService


# {
# 責務: [SemanticEraseDialog: manual maskを作成しcandidateをreview/saveするTk画面]
# フィールド: [source image, mask canvas, fill/query controls, candidate/history state]
# 処理: [1: sourceとmask overlayを表示する, 2: strokeでmaskを修正する, 3: async eraseを実行してreviewする]
# }
class SemanticEraseDialog(tk.Toplevel):
    # {
    # 責務: [__init__: source imageとserviceをdialogへ接続する]
    # 処理: [1: source imageをdecodeする, 2: controls/canvasを作る, 3: polling queueを開始する]
    # 引数: [master: parent Tk widget, image_path: selected source, service: pluggable erase pipeline]
    # 戻り値: []
    # エラー: [OSError: source imageをdecodeできない場合]
    # }
    def __init__(
        self,
        master,
        image_path: str | Path,
        service: SemanticEraseService | None = None,
    ):
        source_path = Path(image_path).expanduser().absolute()
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("source image must be a regular file")
        try:
            with Image.open(source_path) as opened:
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("selected image exceeds the 50 megapixel safety limit")
                decoded_source = opened.convert("RGB")
        except Image.DecompressionBombError as exc:
            raise ValueError("selected image exceeds Pillow's decompression safety limit") from exc
        super().__init__(master)
        self.title("Semantic Erase Retouch")
        self.geometry("900x760")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.image_path = source_path
        self.source = decoded_source
        self.service = service or SemanticEraseService()
        self.mask = RLEMask.empty(self.source.width, self.source.height)
        self._stroke_points: list[tuple[float, float]] = []
        self._erase_stroke = False
        self._preview_output: Path | None = None
        self._photo = None
        self._display_box = (0, 0, 1, 1)
        self._busy = False
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._history = None
        self._operation_id = None
        ttk.Label(
            self,
            text="ブラシで消去範囲を塗り、queryと補完方針を選んでください。元画像は常に保持されます。",
            wraplength=860,
        ).pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Label(
            self,
            text="標準構成はmanual mask + OpenCV局所補間です。text-only検出やskin/cloth補完にはhost側model adapterが必要です。",
            wraplength=860,
        ).pack(anchor="w", padx=10, pady=(0, 6))
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=10)
        ttk.Label(controls, text="Remove query").grid(row=0, column=0, sticky="w")
        self.query = tk.StringVar(self, value="remove selected region")
        ttk.Entry(controls, textvariable=self.query, width=34).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Label(controls, text="Fill").grid(row=0, column=2, sticky="w", padx=(6, 0))
        self.fill = tk.StringVar(self, value=FillPolicy.AUTO.value)
        ttk.Combobox(
            controls,
            textvariable=self.fill,
            values=tuple(item.value for item in FillPolicy),
            state="readonly",
            width=22,
        ).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Label(controls, text="Custom fill").grid(row=1, column=0, sticky="w")
        self.fill_instruction = tk.StringVar(self)
        ttk.Entry(controls, textvariable=self.fill_instruction).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=4
        )
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        brush_row = ttk.Frame(self)
        brush_row.pack(fill="x", padx=10, pady=4)
        self.erase_mode = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(
            brush_row, text="Maskから消す（消去ブラシ）", variable=self.erase_mode
        ).pack(side="left")
        ttk.Button(brush_row, text="MaskをClear", command=self.clear_mask).pack(side="left", padx=5)
        ttk.Button(brush_row, text="元画像 / Candidate", command=self.toggle_preview).pack(
            side="left", padx=5
        )
        self.status = tk.StringVar(self, value="赤色overlayが消去候補です。")
        ttk.Label(brush_row, textvariable=self.status).pack(side="left", padx=8)
        self.canvas = tk.Canvas(
            self, background="#252525", width=860, height=570, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=4)
        self.canvas.bind("<Configure>", self._render)
        self.canvas.bind("<ButtonPress-1>", self._begin_stroke)
        self.canvas.bind("<B1-Motion>", self._continue_stroke)
        self.canvas.bind("<ButtonRelease-1>", self._finish_stroke)
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=(4, 10))
        self.apply_button = ttk.Button(actions, text="Candidateを作成", command=self.apply)
        self.apply_button.pack(side="left")
        self.replay_button = ttk.Button(
            actions,
            text="選択operationを再実行",
            command=self.replay_operation,
            state="disabled",
        )
        self.replay_button.pack(side="left", padx=5)
        self.save_button = ttk.Button(
            actions, text="確認して別名保存…", command=self.save_copy, state="disabled"
        )
        self.save_button.pack(side="left", padx=5)
        ttk.Button(actions, text="Undo", command=self.undo).pack(side="right", padx=4)
        ttk.Button(actions, text="Redo", command=self.redo).pack(side="right", padx=4)
        self._render()
        self._after = self.after(80, self._poll)
        self.bind("<Destroy>", self._destroyed, add=True)

    # {
    # 責務: [_render: source/candidate imageとmanual mask overlayをcanvasへ描画する]
    # 処理: [1: canvas boundsへ画像fitする, 2: mask overlayを重ねて表示する]
    # 引数: [event: optional Tk resize event]
    # 戻り値: []
    # }
    def _render(self, event=None):
        if not hasattr(self, "canvas"):
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        selected_path = (
            self._preview_output
            if getattr(self, "_show_candidate", False)
            and self._preview_output
            and self._preview_output.exists()
            else None
        )
        if selected_path:
            with Image.open(selected_path) as opened:
                base = opened.convert("RGB")
        else:
            base = self.source.copy()
        view = ImageOps.contain(base, (canvas_width, canvas_height))
        left = (canvas_width - view.width) // 2
        top = (canvas_height - view.height) // 2
        self._display_box = (left, top, view.width, view.height)
        if not selected_path and self.mask.area:
            overlay = Image.new("RGBA", view.size, (255, 0, 0, 0))
            mask_l = Image.frombytes(
                "L", (self.mask.width, self.mask.height), self.mask.to_binary_bytes()
            ).point(lambda value: 255 if value else 0)
            overlay_mask = mask_l.resize(view.size, Image.Resampling.NEAREST)
            overlay.putalpha(overlay_mask.point(lambda value: value * 110 // 255))
            view = Image.alpha_composite(view.convert("RGBA"), overlay).convert("RGB")
        self._photo = ImageTk.PhotoImage(view, master=self)
        self.canvas.delete("all")
        self.canvas.create_image(left, top, image=self._photo, anchor="nw")
        if event is not None and hasattr(event, "width"):
            self.canvas.update_idletasks()

    # {
    # 責務: [_canvas_to_normalized: canvas pointerをimage-relative coordinateへ写す]
    # 処理: [1: displayed image boundsを確認する, 2: clampしてnormalized pointを返す]
    # 引数: [event: Tk mouse event]
    # 戻り値: [point: normalized x/yまたはNone]
    # }
    def _canvas_to_normalized(self, event):
        left, top, width, height = self._display_box
        x = (event.x - left) / max(1, width)
        y = (event.y - top) / max(1, height)
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            return None
        return (x, y)

    # {
    # 責務: [_begin_stroke: mask brush strokeを開始する]
    # 処理: [1: pointer coordinateを正規化する, 2: erase/add modeをsnapshotする]
    # 引数: [event: Tk mouse event]
    # 戻り値: []
    # }
    def _begin_stroke(self, event):
        point = self._canvas_to_normalized(event)
        if point is not None and self._preview_output is None and not self._busy:
            self._stroke_points = [point]
            self._erase_stroke = self.erase_mode.get()

    # {
    # 責務: [_continue_stroke: pointer pathをpreview canvasへ追加する]
    # 処理: [1: pointを画像boundsへ変換する, 2: red stroke guideを描く]
    # 引数: [event: Tk mouse event]
    # 戻り値: []
    # }
    def _continue_stroke(self, event):
        point = self._canvas_to_normalized(event)
        if point is None or not self._stroke_points:
            return
        self._stroke_points.append(point)
        left, top, width, height = self._display_box
        first, second = self._stroke_points[-2:]
        self.canvas.create_line(
            left + first[0] * width,
            top + first[1] * height,
            left + second[0] * width,
            top + second[1] * height,
            fill="#00ffbf" if self._erase_stroke else "#ff3344",
            width=14,
            capstyle="round",
        )

    # {
    # 責務: [_finish_stroke: pointer pathをRLE maskへ反映する]
    # 処理: [1: display scaleからbrush radiusを算出する, 2: add/subtract strokeを適用する, 3: overlayを再描画する]
    # 引数: [event: Tk mouse event]
    # 戻り値: []
    # }
    def _finish_stroke(self, event):
        point = self._canvas_to_normalized(event)
        if point is not None and self._stroke_points:
            self._stroke_points.append(point)
            radius = 7 / max(1, min(self._display_box[2:]))
            try:
                from comfyui_support_tools.shared.semantic_erase.backends import (
                    edit_mask_stroke,
                )

                self.mask = edit_mask_stroke(
                    self.mask,
                    tuple(self._stroke_points),
                    radius=max(radius, 1 / min(self.source.size)),
                    erase=self._erase_stroke,
                )
            except ValueError as exc:
                self.status.set(str(exc))
        self._stroke_points = []
        self._render()

    # {
    # 責務: [clear_mask: 手動maskを空に戻す]
    # 処理: [1: source sizeの空maskを作る, 2: viewを更新する]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def clear_mask(self):
        self.mask = RLEMask.empty(self.source.width, self.source.height)
        self._preview_output = None
        self.save_button.configure(state="disabled")
        self._render()

    # {
    # 責務: [apply: erase requestをworker threadで実行してreview candidateを作成する]
    # 処理: [1: query/mask/fill policyを検証する, 2: UIをbusyへ切替える, 3: workerを開始する]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def apply(self):
        if self._busy:
            return
        if not self.mask.area:
            messagebox.showinfo(
                "Mask required", "まず消去範囲を赤色で塗ってください。", parent=self
            )
            return
        try:
            fill = FillPolicy(self.fill.get())
            instruction = self.fill_instruction.get().strip() or None
            if instruction and fill is FillPolicy.AUTO:
                fill = FillPolicy.CUSTOM
            target = SemanticEraseTarget(
                query=self.query.get().strip(),
                mask=self.mask,
                match_policy=MatchPolicy.REMOVE_ALL,
                fill_policy=fill,
                fill_instruction=instruction,
            )
            request = EraseRequest(
                image_path=str(self.image_path),
                target=target,
                mode=EraseMode.REVIEW_UNCERTAIN,
            )
        except ValueError as exc:
            messagebox.showerror("Invalid request", str(exc), parent=self)
            return
        self._busy = True
        self.apply_button.configure(state="disabled")
        self.status.set("局所補完と保存差分を確認しています…")
        threading.Thread(target=self._run_request, args=(request,), daemon=True).start()

    # {
    # 責務: [replay_operation: saved query/mask/policyを再実行する]
    # 処理: [1: last operation/historyを確認する, 2: UIをbusyへ切替える, 3: hash-guarded workerを開始する]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def replay_operation(self):
        if self._busy or not self._operation_id or not self._history:
            return
        self._busy = True
        self.apply_button.configure(state="disabled")
        self.replay_button.configure(state="disabled")
        self.status.set("保存済operationを再実行しています…")
        threading.Thread(
            target=self._run_replay,
            args=(self._operation_id, self._history.root),
            daemon=True,
        ).start()

    # {
    # 責務: [_run_replay: history replayをworker threadで実行してresult eventを送る]
    # 処理: [1: service.replayを呼ぶ, 2: result/errorをqueueへ渡す]
    # 引数: [operation_id: saved operation ID, history_root: operation archive]
    # 戻り値: []
    # }
    def _run_replay(self, operation_id: str, history_root: Path):
        try:
            result = self.service.replay(self.image_path, history_root, operation_id)
            self._events.put(("result", result))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    # {
    # 責務: [_run_request: worker threadでpipelineを呼びUI event queueへ結果を渡す]
    # 処理: [1: service.processを実行する, 2: result/errorをqueueへenqueueする]
    # 引数: [request: validated erase request]
    # 戻り値: []
    # }
    def _run_request(self, request: EraseRequest):
        try:
            result = self.service.process(request)
            self._events.put(("result", result))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    # {
    # 責務: [_poll: workerからの結果をTk UI threadで適用する]
    # 処理: [1: event queueをdrainする, 2: preview/stateを更新する, 3: pollを再scheduleする]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def _poll(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                self._busy = False
                self.apply_button.configure(state="normal")
                if kind == "error":
                    self.replay_button.configure(
                        state="normal" if self._operation_id else "disabled"
                    )
                    self.status.set("Candidate作成に失敗しました。元画像は保持されています。")
                    messagebox.showerror("Semantic Erase", str(payload), parent=self)
                    continue
                result = payload
                self._preview_output = Path(result.output_path)
                self._operation_id = result.operation_id
                self._show_candidate = True
                self._history = EraseHistoryStore(self._preview_output.parent)
                self.save_button.configure(state="normal")
                self.replay_button.configure(state="normal")
                scores = result.candidate_evaluations[0]
                details = [
                    f"preview / preserve={scores.preservation_score:.3f}",
                    f"boundary={scores.boundary_score:.3f}",
                    f"residual={scores.residual_score if scores.residual_score is not None else 'unverified'}",
                    f"backend={result.backend_id}",
                    *result.backend_warnings,
                ]
                self.status.set("; ".join(details))
                self._render()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._after = self.after(80, self._poll)

    # {
    # 責務: [toggle_preview: sourceとcandidate previewを切り替える]
    # 処理: [1: current preview pointerを切替える, 2: canvasを描き直す]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def toggle_preview(self):
        if self._preview_output is not None:
            self._show_candidate = not getattr(self, "_show_candidate", False)
            self._render()

    # {
    # 責務: [save_copy: reviewed candidateをユーザー指定先へcopyする]
    # 処理: [1: destinationを選ぶ, 2: sourceと別pathであることを確認する, 3: image copyを保存する]
    # 引数: [self: dialog]
    # 戻り値: []
    # エラー: [OSError: output copyに失敗した場合]
    # }
    def save_copy(self):
        if not self._preview_output or not self._preview_output.is_file():
            return
        target = filedialog.asksaveasfilename(
            parent=self,
            initialfile=f"{self.image_path.stem}.semantic-erase.png",
            defaultextension=".png",
            filetypes=(("PNG image", "*.png"),),
        )
        if not target:
            return
        destination = Path(target).expanduser().absolute()
        same_asset = destination.resolve() == self.image_path.resolve()
        if destination.exists() and self.image_path.exists():
            try:
                same_asset = same_asset or os.path.samefile(destination, self.image_path)
            except OSError:
                pass
        if same_asset or destination.is_symlink():
            messagebox.showerror(
                "Unsafe destination", "元画像やsymlinkへ保存できません。", parent=self
            )
            return
        if destination.exists() and not messagebox.askyesno(
            "Overwrite copy?", f"{destination.name}を置き換えますか？", parent=self
        ):
            return
        staged_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as staged:
                staged_path = Path(staged.name)
                with self._preview_output.open("rb") as source:
                    shutil.copyfileobj(source, staged)
                staged.flush()
                os.fsync(staged.fileno())
            os.replace(staged_path, destination)
            self.status.set(f"別copyを保存しました: {destination.name}")
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)

    # {
    # 責務: [undo: history pointerを戻してsource/candidateを表示する]
    # 処理: [1: active pointerを戻す, 2: active image previewを更新する]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def undo(self):
        if self._history:
            self._preview_output = self._history.undo()
            self._show_candidate = self._preview_output is not None
            self.save_button.configure(state="normal" if self._show_candidate else "disabled")
            self._render()

    # {
    # 責務: [redo: history pointerを進めてcandidateを表示する]
    # 処理: [1: active pointerを進める, 2: active image previewを更新する]
    # 引数: [self: dialog]
    # 戻り値: []
    # }
    def redo(self):
        if self._history:
            self._preview_output = self._history.redo()
            self._show_candidate = self._preview_output is not None
            self.save_button.configure(state="normal" if self._show_candidate else "disabled")
            self._render()

    # {
    # 責務: [_destroyed: polling callbackをcancelしてUI resourceをreleaseする]
    # 処理: [1: dialog destroy eventを確認する, 2: scheduled pollをcancelする]
    # 引数: [event: Tk destroy event]
    # 戻り値: []
    # }
    def _destroyed(self, event):
        if event.widget is self and hasattr(self, "_after"):
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
