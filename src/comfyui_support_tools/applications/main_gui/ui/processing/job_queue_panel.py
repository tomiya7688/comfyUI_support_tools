"""Compact Job Queue view. It never starts backend work itself."""

from datetime import datetime
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from comfyui_support_tools.shared.contracts.job_contracts import ACTIVE_JOB_STATES


STATE_LABELS = {
    "queued": "待機",
    "running": "実行中",
    "done": "完了",
    "error": "エラー",
    "cancelled": "取消",
}


# {
# 責務: [JobQueuePanel: shared JobSnapshot historyを表示しactive job cancelを提供する]
# フィールド: [commander/log, Treeview/detail/cancel/retry controls, refresh timer, closed/signature state]
# }
class JobQueuePanel(ttk.Frame):
    # {
    #   責務: [__init__: bounded refresh timer付きjob table/detail UIを構築する]
    #   処理: [columns/buttons/detailsを作り、selection eventとdestroy cleanupをbindする]
    #   引数: [self: panel, master: parent widget, commander: job queue UI API, log: message callback]
    #   戻り値: [なし]
    #   副作用: [Tk controlsを作り180ms refresh timerをscheduleする]
    # }
    def __init__(self, master, commander, log):
        super().__init__(master)
        self.commander = commander
        self.log = log
        self._closed = False
        self._last = None
        self.tree = ttk.Treeview(
            self,
            show="headings",
            selectmode="browse",
            columns=("state", "progress", "action", "source", "started", "message"),
            height=4,
        )
        for key, title, width in (
            ("state", "状態", 65),
            ("progress", "進捗", 65),
            ("action", "Action", 150),
            ("source", "Source", 180),
            ("started", "開始", 80),
            ("message", "Message", 260),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=55, stretch=key in ("source", "message"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_details())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 0))
        self.cancel_button = ttk.Button(
            buttons, text="停止", command=self.cancel_selected, state="disabled"
        )
        self.cancel_button.pack(side="left")
        self.retry_button = ttk.Button(buttons, text="再実行（handler未接続）", state="disabled")
        self.retry_button.pack(side="left", padx=4)
        self.detail = ScrolledText(self, height=3, wrap="word", state="disabled")
        self.detail.pack(fill="x", pady=(4, 0))
        self._after = self.after(180, self._tick)
        self.bind("<Destroy>", self._destroyed, add=True)

    # {
    #   責務: [_tick: panelがopenの間snapshotsを180ms間隔でrefreshする]
    #   処理: [timer IDをclearしclosedでなければrefresh後に次tickをscheduleする]
    #   引数: [self: panel]
    #   戻り値: [なし]
    #   副作用: [Tk after timerを更新する]
    # }
    def _tick(self):
        self._after = None
        if self._closed:
            return
        self.refresh()
        if not self._closed:
            self._after = self.after(180, self._tick)

    # {
    #   責務: [refresh: job snapshotsが変化した場合だけtree rowsとselection detailsを更新する]
    #   処理: [signatureを比較し削除/更新/挿入し、selected job IDを可能なら維持する]
    #   引数: [self: panel]
    #   戻り値: [なし。closedなら何もしない]
    #   副作用: [JobUiCommanderを読み、Treeview/detail stateを更新する]
    # }
    def refresh(self):
        if self._closed:
            return
        snapshots = self.commander.snapshots()
        signature = tuple(
            (job.id, job.state, job.progress, job.message, job.error, job.logs, job.backend_job_id)
            for job in snapshots
        )
        if signature != self._last:
            selected = self.tree.selection()
            selected_id = selected[0] if selected else ""
            current = set(self.tree.get_children())
            wanted = {job.id for job in snapshots}
            for job_id in current - wanted:
                self.tree.delete(job_id)
            for index, job in enumerate(snapshots):
                values = self._values(job)
                if self.tree.exists(job.id):
                    self.tree.item(job.id, values=values)
                    self.tree.move(job.id, "", index)
                else:
                    self.tree.insert("", "end", iid=job.id, values=values)
            if selected_id and self.tree.exists(selected_id):
                self.tree.selection_set(selected_id)
            self._last = signature
            self._show_details()

    # {
    #   責務: [_values: JobSnapshotからtable表示用state/progress/action/source/time/messageを整形する]
    #   処理: [None progressのlabelを選びsource countと開始時刻をformatしtext長を制限する]
    #   引数: [self: panel, job: JobSnapshot]
    #   戻り値: [tuple[str,...]: six Treeview column values]
    # }
    def _values(self, job):
        if job.progress is None:
            progress = "—" if job.state != "running" else "不定"
        else:
            progress = f"{job.progress:.0%}"
        source = job.source_names[0] if job.source_names else "—"
        if len(job.source_names) > 1:
            source += f" +{len(job.source_names) - 1}"
        started = (
            datetime.fromtimestamp(job.started_at).strftime("%H:%M:%S") if job.started_at else "—"
        )
        message = job.error or job.message
        return (
            STATE_LABELS.get(job.state, job.state),
            progress,
            job.action,
            source[:80],
            started,
            message[:120],
        )

    # {
    #   責務: [_selected: current tree selectionに対応する最新JobSnapshotを探す]
    #   処理: [selectionなしならNone、あればcurrent snapshotsからID一致jobを返す]
    #   引数: [self: panel]
    #   戻り値: [JobSnapshotまたはNone]
    # }
    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            return None
        job_id = selection[0]
        return next((job for job in self.commander.snapshots() if job.id == job_id), None)

    # {
    #   責務: [_show_details: selected jobのidentity/timestamps/error/logをdetail paneへ表示する]
    #   処理: [detail textを置換しactive+cancellable時だけcancelを有効化、retryは常にdisableする]
    #   引数: [self: panel]
    #   戻り値: [なし]
    #   副作用: [Text/button widget stateを更新する]
    # }
    def _show_details(self):
        job = self._selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if job:
            lines = [
                f"ID: {job.id}",
                f"kind: {job.kind}",
                f"backend_job_id: {job.backend_job_id or '—'}",
                f"source count: {len(job.source_ids) or len(job.source_names)}",
                f"created: {datetime.fromtimestamp(job.created_at).isoformat(timespec='seconds')}",
            ]
            if job.finished_at:
                lines.append(
                    f"finished: {datetime.fromtimestamp(job.finished_at).isoformat(timespec='seconds')}"
                )
            if job.retry_of:
                lines.append(f"retry_of: {job.retry_of}")
            if job.error:
                lines.append("error: " + job.error)
            if job.logs:
                lines.append("")
                lines.extend(job.logs)
            self.detail.insert("1.0", "\n".join(lines))
            self.cancel_button.configure(
                state="normal" if job.cancellable and job.state in ACTIVE_JOB_STATES else "disabled"
            )
            self.retry_button.configure(state="disabled")
        else:
            self.cancel_button.configure(state="disabled")
            self.retry_button.configure(state="disabled")
        self.detail.configure(state="disabled")

    # {
    #   責務: [cancel_selected: selected cancellable jobの停止を依頼し成功時logを出す]
    #   処理: [current snapshotを読み、commander.cancelがtrueの場合logする]
    #   引数: [self: panel]
    #   戻り値: [なし]
    #   副作用: [job cancellationを要求し、受理時UI log callbackを呼ぶ]
    # }
    def cancel_selected(self):
        job = self._selected()
        if job and self.commander.cancel(job.id):
            self.log(f"Job停止要求: {job.action}")

    # {
    #   責務: [close: refresh timerをcancelしpanelをclosedにする]
    #   処理: [重複closeを防ぎafter IDがある場合だけafter_cancelする]
    #   引数: [self: panel]
    #   戻り値: [なし]
    #   副作用: [scheduled Tk callbackを取り消す]
    # }
    def close(self):
        if not self._closed:
            self._closed = True
            if self._after is not None:
                self.after_cancel(self._after)
                self._after = None

    # {
    #   責務: [_destroyed: 自身のDestroy eventだけを処理しclose cleanupを呼ぶ]
    #   処理: [event.widgetがpanelならcloseする]
    #   引数: [self: panel, event: Tk Destroy event]
    #   戻り値: [None]
    # }
    def _destroyed(self, event):
        if event.widget is self:
            self.close()
