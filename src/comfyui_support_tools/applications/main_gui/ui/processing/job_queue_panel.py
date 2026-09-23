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
        self.cancel_button = ttk.Button(buttons, text="停止", command=self.cancel_selected, state="disabled")
        self.cancel_button.pack(side="left")
        self.retry_button = ttk.Button(buttons, text="再実行（handler未接続）", state="disabled")
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
    def _values(self, job):
        if job.progress is None:
            progress = "—" if job.state != "running" else "不定"
        else:
            progress = f"{job.progress:.0%}"
        source = job.source_names[0] if job.source_names else "—"
        if len(job.source_names) > 1:
            source += f" +{len(job.source_names)-1}"
        started = datetime.fromtimestamp(job.started_at).strftime("%H:%M:%S") if job.started_at else "—"
        message = job.error or job.message
        return (STATE_LABELS.get(job.state, job.state), progress, job.action, source[:80], started, message[:120])

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
                lines.append(f"finished: {datetime.fromtimestamp(job.finished_at).isoformat(timespec='seconds')}")
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

    def cancel_selected(self):
        job = self._selected()
        if job and self.commander.cancel(job.id):
            self.log(f"Job停止要求: {job.action}")

    def close(self):
        if not self._closed:
            self._closed = True
            if self._after is not None:
                self.after_cancel(self._after)
                self._after = None

    def _destroyed(self, event):
        if event.widget is self:
            self.close()
