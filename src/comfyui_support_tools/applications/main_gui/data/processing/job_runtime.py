"""Thread-safe bounded job runtime shared by local IO adapters.

Workers register a job, then wait for a concurrency slot. The runtime never
executes backend-specific work itself and never touches Tk.
"""

from collections import deque
from dataclasses import dataclass, field
import math
from threading import Condition, Event
import time
import uuid

from comfyui_support_tools.shared.contracts.job_contracts import (
    JobSnapshot,
    TERMINAL_JOB_STATES,
)

MAX_LOG_LINES = 50
MAX_LOG_CHARS = 400
MAX_SOURCES = 100


# {
# 責務: [_JobRecord: runtime内部のmutable job lifecycle stateを保持する]
# フィールド: [job identity/sequence/kind/action/state/progress, timestamps, sources, backend ID, message/error, retry flags/log deque]
# }
@dataclass
class _JobRecord:
    id: str
    sequence: int
    kind: str
    action: str
    state: str
    progress: float | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    source_ids: tuple[str, ...]
    source_names: tuple[str, ...]
    backend_job_id: str
    message: str
    error: str
    cancellable: bool
    retryable: bool
    retry_of: str
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))


# {
# 責務: [JobRuntime: bounded concurrency、FIFO queue、cancellationとsnapshot historyをthread-safeに管理する]
# フィールド: [max_concurrent/history_limit, condition, records, queue, running IDs, cancel events, closed/sequence state]
# }
class JobRuntime:
    # {
    #   責務: [__init__: concurrency/history limitsを検証してruntime stateを初期化する]
    #   処理: [limitを保存しcondition、record/queue/running/cancel containersを作る]
    #   引数: [self: runtime, max_concurrent: 同時worker上限1..16, history_limit: 保持上限10..1000]
    #   戻り値: [なし]
    #   エラー: [ValueError: concurrency/history limitが範囲外]
    # }
    def __init__(self, max_concurrent: int = 2, history_limit: int = 100):
        if not 1 <= max_concurrent <= 16:
            raise ValueError("max_concurrent must be 1..16")
        if not 10 <= history_limit <= 1000:
            raise ValueError("history_limit must be 10..1000")
        self.max_concurrent = max_concurrent
        self.history_limit = history_limit
        self._condition = Condition()
        self._records: dict[str, _JobRecord] = {}
        self._queue: deque[str] = deque()
        self._running: set[str] = set()
        self._cancel: dict[str, Event] = {}
        self._closed = False
        self._sequence = 0

    # {
    #   責務: [create: queued JobSnapshotを作りFIFO queueへ登録する]
    #   処理: [text/source/backend ID boundsを検証しID・record・cancel eventを作り、terminal historyをtrimする]
    #   引数: [self: runtime, kind/action: job labels, source_ids/names: optional source tuples, cancel_event: worker event, backend_job_id/retryable/retry_of: retry metadata]
    #   戻り値: [job_id: new local job identifier]
    #   エラー: [ValueError: request無効またはruntime closed]
    #   副作用: [queue/snapshot historyを更新しwaiting workerへnotifyする]
    # }
    def create(
        self,
        kind: str,
        action: str,
        *,
        source_ids=(),
        source_names=(),
        cancel_event: Event | None = None,
        backend_job_id: str = "",
        retryable: bool = False,
        retry_of: str = "",
    ) -> str:
        ids, names = tuple(source_ids), tuple(source_names)
        if (
            not kind.strip()
            or not action.strip()
            or len(ids) > MAX_SOURCES
            or len(names) > MAX_SOURCES
            or len(backend_job_id) > 256
        ):
            raise ValueError("Invalid job request")
        with self._condition:
            if self._closed:
                raise ValueError("Job runtime is closed")
            self._sequence += 1
            now = time.time()
            job_id = "job-" + uuid.uuid4().hex[:12]
            record = _JobRecord(
                job_id,
                self._sequence,
                kind[:80],
                action[:160],
                "queued",
                None,
                now,
                None,
                None,
                tuple(str(value)[:256] for value in ids),
                tuple(str(value)[:256] for value in names),
                backend_job_id,
                "待機中",
                "",
                True,
                bool(retryable),
                str(retry_of)[:80],
            )
            record.logs.append("queued")
            self._records[job_id] = record
            self._cancel[job_id] = cancel_event or Event()
            self._queue.append(job_id)
            self._trim_locked()
            self._condition.notify_all()
            return job_id

    # {
    #   責務: [wait_start: queued jobにFIFO順でconcurrency slotが空くまで待つ]
    #   処理: [cancel/close/terminal stateを確認し、先頭jobならrunningへ移行してstart timeを記録する]
    #   引数: [self: runtime, job_id: registered job identifier]
    #   戻り値: [started: slotを取得した場合true、job失効/cancel時false]
    #   副作用: [queue/running/record stateを更新しCondition上で待機またはnotifyする]
    # }
    def wait_start(self, job_id: str) -> bool:
        with self._condition:
            while True:
                record = self._records.get(job_id)
                cancel = self._cancel.get(job_id)
                if record is None or cancel is None:
                    return False
                if record.state in TERMINAL_JOB_STATES:
                    return False
                if self._closed or cancel.is_set():
                    self._finish_locked(record, "cancelled", "開始前にキャンセルしました", "")
                    return False
                if (
                    record.state == "queued"
                    and self._queue
                    and self._queue[0] == job_id
                    and len(self._running) < self.max_concurrent
                ):
                    self._queue.popleft()
                    self._running.add(job_id)
                    record.state = "running"
                    record.started_at = time.time()
                    record.message = "実行中"
                    record.logs.append("running")
                    self._condition.notify_all()
                    return True
                self._condition.wait(0.05)

    # {
    #   責務: [update: active jobのprogress/message/logをbounded limitsで更新する]
    #   処理: [progressのfinite 0..1検証後、terminal/unknown jobは無視し各field長を制限する]
    #   引数: [self: runtime, job_id: target, progress: optional fraction, message: user status, log: bounded log line]
    #   戻り値: [なし]
    #   エラー: [ValueError: progressがNoneまたはfinite 0..1でない]
    # }
    def update(
        self, job_id: str, progress: float | None = None, message: str = "", log: str = ""
    ) -> None:
        if progress is not None and (not math.isfinite(progress) or not 0 <= progress <= 1):
            raise ValueError("progress must be None or a finite value in 0..1")
        with self._condition:
            record = self._records.get(job_id)
            if record is None or record.state in TERMINAL_JOB_STATES:
                return
            if progress is not None:
                record.progress = progress
            if message:
                record.message = str(message)[:300]
            if log:
                record.logs.append(str(log)[:MAX_LOG_CHARS])

    # {
    #   責務: [set_backend_job_id: local jobへbackend側identifierを保存する]
    #   処理: [backend ID長を制限し、存在するjob recordを更新する]
    #   引数: [self: runtime, job_id: local ID, backend_job_id: backend ID]
    #   戻り値: [なし]
    #   エラー: [ValueError: backend IDが256文字超過, KeyError: jobが存在しない]
    # }
    def set_backend_job_id(self, job_id: str, backend_job_id: str) -> None:
        if len(backend_job_id) > 256:
            raise ValueError("backend_job_id is too long")
        with self._condition:
            record = self._records.get(job_id)
            if record is None:
                raise KeyError(job_id)
            record.backend_job_id = backend_job_id

    # {
    #   責務: [finish: active jobをdone/error/cancelled terminal stateにする]
    #   処理: [terminal stateを検証し、running/queueから外してrecordとhistoryを更新する]
    #   引数: [self: runtime, job_id: target, state: terminal state, message/error: final descriptions]
    #   戻り値: [なし]
    #   エラー: [ValueError: stateがterminal stateでない]
    #   副作用: [Conditionをnotifyしhistory limitを維持する]
    # }
    def finish(self, job_id: str, state: str, message: str = "", error: str = "") -> None:
        if state not in TERMINAL_JOB_STATES:
            raise ValueError("terminal state required")
        with self._condition:
            record = self._records.get(job_id)
            if record is None or record.state in TERMINAL_JOB_STATES:
                return
            self._finish_locked(record, state, message, error)
            self._trim_locked()
            self._condition.notify_all()

    # {
    #   責務: [cancel: cancellable jobへcancel eventを送りqueued jobは即時終端させる]
    #   処理: [terminal/unknown/noncancellableはfalse、queuedはcancelled、runningはrequest済みmessageにする]
    #   引数: [self: runtime, job_id: target job identifier]
    #   戻り値: [bool: cancel requestを受け付けた場合true]
    #   副作用: [worker eventとrecord/log、Condition waitersを更新する]
    # }
    def cancel(self, job_id: str) -> bool:
        with self._condition:
            record = self._records.get(job_id)
            cancel = self._cancel.get(job_id)
            if (
                record is None
                or cancel is None
                or record.state in TERMINAL_JOB_STATES
                or not record.cancellable
            ):
                return False
            cancel.set()
            if record.state == "queued":
                self._finish_locked(record, "cancelled", "待機中にキャンセルしました", "")
            else:
                record.message = "停止要求済み — 現在のIO完了/timeoutを待っています"
                record.logs.append("cancel requested")
            self._condition.notify_all()
            return True

    # {
    #   責務: [snapshots: newest-first immutable JobSnapshot tupleを返す]
    #   処理: [created time/sequence降順に内部recordsをsortしてpublic contractへcopyする]
    #   引数: [self: runtime]
    #   戻り値: [JobSnapshot tuple: GUIから読むjob state snapshot]
    # }
    def snapshots(self) -> tuple[JobSnapshot, ...]:
        with self._condition:
            records = sorted(
                self._records.values(),
                key=lambda item: (item.created_at, item.sequence),
                reverse=True,
            )
            return tuple(
                JobSnapshot(
                    record.id,
                    record.kind,
                    record.action,
                    record.state,
                    record.progress,
                    record.created_at,
                    record.started_at,
                    record.finished_at,
                    record.source_ids,
                    record.source_names,
                    record.backend_job_id,
                    record.message,
                    record.error,
                    tuple(record.logs),
                    record.cancellable,
                    record.retryable,
                    record.retry_of,
                )
                for record in records
            )

    # {
    #   責務: [close: runtimeを閉じ全cancel eventをsetしqueued jobsをcancelledにする]
    #   処理: [running jobsには停止要求を記録し、queued jobsはterminal化する]
    #   引数: [self: runtime]
    #   戻り値: [なし。既にclosedなら何もしない]
    #   副作用: [worker event/record/condition stateを更新する]
    # }
    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            for cancel in self._cancel.values():
                cancel.set()
            for record in tuple(self._records.values()):
                if record.state == "queued":
                    self._finish_locked(record, "cancelled", "GUI終了によりキャンセルしました", "")
                elif record.state == "running":
                    record.message = "GUI終了による停止要求済み"
                    record.logs.append("shutdown cancel requested")
            self._condition.notify_all()

    # {
    #   責務: [_finish_locked: lock保持中のjobをterminal stateへ移しslotとqueueを解放する]
    #   処理: [running/queuedから除外しfinished fields/logを更新し、doneならprogressを1にする]
    #   引数: [self: runtime, record: mutable job record, state: terminal state, message/error: final text]
    #   戻り値: [なし]
    #   副作用: [queue/running/record fieldsを書き換える。callerがcondition lockを保持する]
    # }
    def _finish_locked(self, record: _JobRecord, state: str, message: str, error: str) -> None:
        if record.id in self._running:
            self._running.remove(record.id)
        try:
            self._queue.remove(record.id)
        except ValueError:
            pass
        record.state = state
        record.finished_at = time.time()
        if state == "done":
            record.progress = 1.0
        record.message = str(message)[:300] or state
        record.error = str(error)[:500]
        record.logs.append((record.error or record.message)[:MAX_LOG_CHARS])

    # {
    #   責務: [_trim_locked: history_limit超過時に最も古いterminal recordsを除去する]
    #   処理: [active jobsは保持し、terminal jobをcreated time/sequence昇順に削る]
    #   引数: [self: runtime]
    #   戻り値: [なし]
    #   副作用: [recordとcancel event mappingから古いjobを削除する。callerがcondition lockを保持する]
    # }
    def _trim_locked(self) -> None:
        if len(self._records) <= self.history_limit:
            return
        terminal = sorted(
            (record for record in self._records.values() if record.state in TERMINAL_JOB_STATES),
            key=lambda item: (item.created_at, item.sequence),
        )
        for record in terminal:
            if len(self._records) <= self.history_limit:
                break
            self._records.pop(record.id, None)
            self._cancel.pop(record.id, None)
