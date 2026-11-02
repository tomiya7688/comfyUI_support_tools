"""Compact Job Queue view. It never starts backend work itself."""

from datetime import datetime
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from comfyui_support_tools.shared.contracts.job_contracts import ACTIVE_JOB_STATES


STATE_LABELS = {
    "queued": "待機",
    "preparing": "準備中",
    "running": "実行中",
    "pausing": "一時停止中",
    "paused": "一時停止",
    "cancelling": "停止中",
    "resuming": "再開中",
    "retrying": "再試行中",
    "done": "完了",
    "error": "エラー",
    "failed": "失敗",
    "cancelled": "取消",
    "interrupted": "中断",
}


class JobQueuePanel(ttk.Frame):
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
        self.pause_button = ttk.Button(
            buttons, text="一時停止", command=self.pause_selected, state="disabled"
        )
        self.pause_button.pack(side="left", padx=4)
        self.resume_button = ttk.Button(
            buttons, text="再開", command=self.resume_selected, state="disabled"
        )
        self.resume_button.pack(side="left")
        self.retry_button = ttk.Button(
            buttons, text="再実行", command=self.retry_selected, state="disabled"
        )
        self.retry_button.pack(side="left", padx=4)
        self.detail = ScrolledText(self, height=3, wrap="word", state="disabled")
        self.detail.pack(fill="x", pady=(4, 0))
        self._after = self.after(180, self._tick)
        self.bind("<Destroy>", self._destroyed, add=True)

    def _tick(self):
        self._after = None
        if self._closed:
            return
        self.refresh()
        if not self._closed:
            self._after = self.after(180, self._tick)

    def refresh(self):
        if self._closed:
            return
        snapshots = self.commander.snapshots()
        signature = tuple(
            (
                job.id,
                job.state,
                job.progress,
                job.message,
                job.error,
                job.logs,
                job.backend_job_id,
                job.checkpoint_ref,
                job.checkpoint_capability,
                job.manifest_ref,
                job.cancel_capability,
                job.cancellable,
                job.retryable,
                job.shutdown_policy,
                job.partial_result_policy,
                job.completed_items,
                job.pending_items,
                job.failed_items,
                job.artifact_refs,
            )
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

    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            return None
        job_id = selection[0]
        return next((job for job in self.commander.snapshots() if job.id == job_id), None)

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
            lines.append(f"checkpoint: {job.checkpoint_ref or '—'} ({job.checkpoint_capability})")
            lines.append(f"cancel capability: {job.cancel_capability}")
            lines.append(f"shutdown policy: {job.shutdown_policy}")
            if job.manifest_ref:
                lines.append(f"manifest: {job.manifest_ref}")
            if job.completed_items or job.pending_items or job.failed_items:
                lines.append(
                    "items: "
                    f"{len(job.completed_items)} completed, "
                    f"{len(job.pending_items)} pending, "
                    f"{len(job.failed_items)} failed"
                )
            if job.artifact_refs:
                lines.append(f"artifacts: {len(job.artifact_refs)}")
            if job.error:
                lines.append("error: " + job.error)
            if job.logs:
                lines.append("")
                lines.extend(job.logs)
            self.detail.insert("1.0", "\n".join(lines))
            self.cancel_button.configure(
                state="normal" if job.cancellable and job.state in ACTIVE_JOB_STATES else "disabled"
            )
            self.pause_button.configure(
                state=(
                    "normal"
                    if job.checkpoint_capability != "none" and job.state in {"queued", "running"}
                    else "disabled"
                )
            )
            self.resume_button.configure(
                state=(
                    "normal"
                    if job.state == "paused"
                    or (job.state == "interrupted" and job.checkpoint_ref and job.manifest_ref)
                    else "disabled"
                )
            )
            self.retry_button.configure(
                state=(
                    "normal"
                    if job.retryable
                    and job.state in {"error", "failed", "cancelled", "interrupted"}
                    else "disabled"
                )
            )
        else:
            self.cancel_button.configure(state="disabled")
            self.pause_button.configure(state="disabled")
            self.resume_button.configure(state="disabled")
            self.retry_button.configure(state="disabled")
        self.detail.configure(state="disabled")

    def cancel_selected(self):
        job = self._selected()
        if job and self.commander.cancel(job.id):
            self.log(f"Job停止要求: {job.action}")

    # {
    #   責務: [pause_selected: 選択Jobへcheckpoint-based pause要求を送る]
    #   処理: [1: selectionを読む 2: Commanderへpause要求を送る 3: UI logへ記録する]
    #   引数: []
    #   戻り値: []
    # }
    def pause_selected(self):
        job = self._selected()
        if job and self.commander.pause(job.id):
            self.log(f"Job一時停止要求: {job.action}")

    # {
    #   責務: [resume_selected: 選択したpaused Jobを再開する]
    #   処理: [1: selectionを読む 2: Commanderへresume要求を送る 3: UI logへ記録する]
    #   引数: []
    #   戻り値: []
    # }
    def resume_selected(self):
        job = self._selected()
        if job and self.commander.resume(job.id):
            self.log(f"Job再開要求: {job.action}")

    # {
    #   責務: [retry_selected: 選択したretry可能Jobのidempotent再実行を要求する]
    #   処理: [1: selectionを読む 2: Commanderへretry要求を送る 3: 成功時にUI logへ記録する]
    #   引数: []
    #   戻り値: []
    # }
    def retry_selected(self):
        job = self._selected()
        if job:
            retry_job_id = self.commander.retry(job.id)
            if retry_job_id:
                self.log(f"Job再実行: {job.action} → {retry_job_id}")

    def close(self):
        if not self._closed:
            self._closed = True
            if self._after is not None:
                self.after_cancel(self._after)
                self._after = None

    def _destroyed(self, event):
        if event.widget is self:
            self.close()
