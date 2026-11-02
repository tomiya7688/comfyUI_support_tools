"""Checkpoint, retry, and durable recovery controls for the shared Job runtime."""

import time
from collections import deque
from threading import Event

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime_models import (
    MAX_LOG_LINES,
    CancelHandler,
    ResumeHandler,
    RetryHandler,
    _JobRecord,
)
from comfyui_support_tools.shared.contracts.job_contracts import (
    ACTIVE_JOB_STATES,
    TERMINAL_JOB_STATES,
    CancelCapability,
    CheckpointCapability,
    JobSnapshot,
    ShutdownPolicy,
)


# {
#   責務: [JobRuntimeControlMixin: lifecycle extension, resume/retry, snapshot persistenceを管理する]
#   フィールド: [JobRuntimeが提供するlock、records、queue、storeへの内部参照]
#   処理: [pause/checkpoint/resume/retryとrestart recoveryを制御する]
#   補足: [JobRuntimeの内部state契約に結合したprivate mixin]
# }
class JobRuntimeControlMixin:
    # {
    #   責務: [cancellation_token: adapterが協調停止を監視するEvent tokenを返す]
    #   処理: [1: Job IDを照合する 2: runtimeがcancel時に通知するEventを返す]
    #   引数: [job_id: 対象Job ID]
    #   戻り値: [token: thread-safe cancellation Event]
    #   エラー: [KeyError: Job IDが存在しない場合]
    # }
    def cancellation_token(self, job_id: str) -> Event:
        with self._condition:
            token = self._cancel.get(job_id)
            if token is None:
                raise KeyError(job_id)
            return token

    # {
    #   責務: [register_backend_cancel_handler: backendごとの停止要求をJobへ登録する]
    #   処理: [1: Jobの存在を検証する 2: callbackを保持する]
    #   引数: [job_id: 対象Job ID, handler: backend_job_idを受け取る非blocking callback]
    #   戻り値: []
    #   エラー: [KeyError: Jobが履歴に存在しない場合]
    # }
    def register_backend_cancel_handler(self, job_id: str, handler: CancelHandler) -> None:
        self.register_cancel_handler(job_id, handler, CancelCapability.BACKEND)

    # {
    #   責務: [register_cancel_handler: backend/process capability用の停止adapterをJobへ登録する]
    #   処理: [1: capabilityとcallbackを検証する 2: handlerを保存してcancellableを有効にする]
    #   引数: [job_id: 対象Job, handler: 非blocking cancel adapter, capability: backendまたはprocess]
    #   戻り値: []
    #   エラー: [KeyError: Job IDが存在しない場合, ValueError: unsupported capabilityの場合]
    # }
    def register_cancel_handler(
        self,
        job_id: str,
        handler: CancelHandler,
        capability: CancelCapability | str = CancelCapability.BACKEND,
    ) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable")
        capability = CancelCapability(capability)
        if capability not in {CancelCapability.BACKEND, CancelCapability.PROCESS}:
            raise ValueError("Cancel handler capability must be backend or process")
        with self._condition:
            if job_id not in self._records:
                raise KeyError(job_id)
            self._backend_cancel_handlers[job_id] = handler
            self._records[job_id].cancellable = True
            self._records[job_id].cancel_capability = capability.value
            self._persist_locked()

    # {
    #   責務: [finish_current_item_requested: shutdown policyによるitem境界停止要求を照会する]
    #   処理: [1: 対象Job IDがfinish-current-item setにあるかを確認する]
    #   引数: [job_id: 実行中Job ID]
    #   戻り値: [requested: 次item投入を止めるべきか]
    # }
    def finish_current_item_requested(self, job_id: str) -> bool:
        with self._condition:
            return job_id in self._finish_after_item

    # {
    #   責務: [pause: checkpoint対応Jobへ安全な停止境界でのpauseを要求する]
    #   処理: [1: Job capabilityを検証する 2: queuedはpaused、runningはpausingへ遷移する]
    #   引数: [job_id: pauseするJob ID]
    #   戻り値: [requested: pause要求を受理したか]
    # }
    def pause(self, job_id: str) -> bool:
        with self._condition:
            record = self._records.get(job_id)
            if (
                record is None
                or record.state not in {"queued", "preparing", "retrying", "running"}
                or record.checkpoint_capability == CheckpointCapability.NONE.value
            ):
                return False
            if record.state in {"queued", "preparing", "retrying"}:
                self._remove_from_queue_locked(job_id)
                record.state = "paused"
                record.message = "checkpointから一時停止しました"
                record.logs.append("paused before start")
            else:
                record.state = "pausing"
                record.message = "安全なcheckpoint境界で一時停止します"
                record.logs.append("pause requested")
            self._condition.notify_all()
            self._persist_locked()
            return True

    # {
    #   責務: [checkpoint: 進捗itemと再開checkpointを保存する]
    #   処理: [1: capabilityとcheckpoint参照を検証する 2: item/artifact状態を更新する 3: pausingならpausedへ遷移する]
    #   引数: [job_id: 対象Job, checkpoint_ref: 再開地点, completed_items: 完了item, pending_items: 未処理item, failed_items: 失敗item, artifact_refs: 成果物参照]
    #   戻り値: [continue_work: pause要求がなく処理継続できるか]
    # }
    def checkpoint(
        self,
        job_id: str,
        checkpoint_ref: str,
        *,
        completed_items=(),
        pending_items=(),
        failed_items=(),
        artifact_refs=(),
    ) -> bool:
        if not checkpoint_ref or len(checkpoint_ref) > 512:
            raise ValueError("checkpoint_ref must contain 1..512 characters")
        with self._condition:
            record = self._records.get(job_id)
            if record is None:
                raise KeyError(job_id)
            if record.checkpoint_capability == CheckpointCapability.NONE.value:
                raise ValueError("Job does not support checkpoints")
            record.checkpoint_ref = checkpoint_ref
            record.completed_items = self._bounded_item_ids(completed_items)
            record.pending_items = self._bounded_item_ids(pending_items)
            record.failed_items = self._bounded_item_ids(failed_items)
            record.artifact_refs = self._bounded_item_ids(artifact_refs)
            if record.state == "pausing":
                record.state = "paused"
                record.message = "checkpointで一時停止しました"
                record.logs.append("checkpoint saved; paused")
                self._running.discard(job_id)
                self._release_resource_lease_locked(job_id)
                self._condition.notify_all()
                self._persist_locked()
                return False
            self._persist_locked()
            return record.state == "running"

    # {
    #   責務: [wait_if_paused: pauseされたworkerをresumeまたはcancelまで待機させる]
    #   処理: [1: pausedを待つ 2: resume後にbounded concurrency slotを再取得する]
    #   引数: [job_id: workerが実行中のJob ID]
    #   戻り値: [can_continue: workerを再開できるか]
    # }
    def wait_if_paused(self, job_id: str) -> bool:
        with self._condition:
            while True:
                record = self._records.get(job_id)
                cancel = self._cancel.get(job_id)
                if record is None or cancel is None or record.state in TERMINAL_JOB_STATES:
                    return False
                if self._closed:
                    if record.shutdown_policy == ShutdownPolicy.DETACH.value:
                        return record.state == "running"
                    if (
                        record.state == "paused"
                        and record.shutdown_policy == ShutdownPolicy.CHECKPOINT_AND_STOP.value
                    ):
                        self._attached_workers.discard(job_id)
                        return False
                    self._finish_locked(record, "cancelled", "停止しました", "")
                    self._condition.notify_all()
                    return False
                if cancel.is_set():
                    self._finish_locked(record, "cancelled", "停止しました", "")
                    self._condition.notify_all()
                    return False
                if record.state in {"pausing", "paused", "resuming"}:
                    self._condition.wait(0.05)
                    continue
                if record.state == "queued":
                    if (
                        self._queue
                        and self._queue[0] == job_id
                        and len(self._running) < self.max_concurrent
                    ):
                        if not self._try_acquire_resource_lease_locked(job_id):
                            self._condition.wait(0.05)
                            continue
                        self._queue.popleft()
                        self._running.add(job_id)
                        record.state = "running"
                        record.message = "再開しました"
                        record.logs.append("resumed")
                        self._condition.notify_all()
                        self._persist_locked()
                        return True
                    self._condition.wait(0.05)
                    continue
                return record.state == "running"

    # {
    #   責務: [resume: checkpoint済みpaused Jobをqueueへ戻す]
    #   処理: [1: stateとcheckpointを検証する 2: FIFO queueへ追加してworkerを通知する]
    #   引数: [job_id: 再開するJob ID]
    #   戻り値: [resumed: 再開要求を受理したか]
    # }
    def resume(self, job_id: str) -> bool:
        resume_handler = None
        restored_snapshot = None
        with self._condition:
            record = self._records.get(job_id)
            if (
                record is None
                or record.state not in {"paused", "interrupted"}
                or record.checkpoint_capability == CheckpointCapability.NONE.value
                or (record.started_at is not None and not record.checkpoint_ref)
            ):
                return False
            if record.state == "interrupted":
                if not record.manifest_ref:
                    return False
                resume_handler = self._resume_handlers.get(record.kind)
                if resume_handler is None:
                    return False
            elif job_id not in self._attached_workers:
                if not record.manifest_ref:
                    return False
                resume_handler = self._resume_handlers.get(record.kind)
                if resume_handler is None:
                    return False
            record.state = "queued"
            record.message = "再開待ち"
            record.logs.append("resume requested")
            self._queue.append(job_id)
            self._condition.notify_all()
            self._persist_locked()
            if resume_handler is not None:
                restored_snapshot = self._snapshot_locked(record)
        if resume_handler is not None:
            try:
                resume_handler(restored_snapshot)
            except Exception as exc:
                with self._condition:
                    record = self._records.get(job_id)
                    if record is not None and record.state == "queued":
                        self._remove_from_queue_locked(job_id)
                        record.state = "interrupted"
                        record.message = "再開adapterを起動できませんでした"
                        record.logs.append(f"resume adapter failed: {type(exc).__name__}")
                        self._persist_locked()
                return False
        return True

    # {
    #   責務: [register_resume_handler: restart後にmanifestからJob入力を復元するadapterを登録する]
    #   処理: [1: kindとcallbackを検証する 2: runtime handler registryへ保存する]
    #   引数: [kind: Job種類, handler: persisted manifestを読み込んでworkerを起動するcallback]
    #   戻り値: []
    # }
    def register_resume_handler(self, kind: str, handler: ResumeHandler) -> None:
        if not kind.strip() or not callable(handler):
            raise ValueError("kind and callable handler are required")
        with self._condition:
            self._resume_handlers[kind] = handler

    # {
    #   責務: [register_retry_handler: kind単位のidempotent retry adapterを登録する]
    #   処理: [1: kindとcallbackを検証する 2: runtime handler registryへ保存する]
    #   引数: [kind: Job種類, handler: retry元snapshotからchild Jobを作るcallback]
    #   戻り値: []
    # }
    def register_retry_handler(self, kind: str, handler: RetryHandler) -> None:
        if not kind.strip() or not callable(handler):
            raise ValueError("kind and callable handler are required")
        with self._condition:
            self._retry_handlers[kind] = handler

    # {
    #   責務: [retry: operation IDとlineageを保つidempotent retryを要求する]
    #   処理: [1: retry可能性とmanifestを検証する 2: 既存childを返す 3: handlerでchildを作る 4: lineageを検証する]
    #   引数: [job_id: retry元Job ID]
    #   戻り値: [retry_job_id: 既存または新規child Job ID、未対応ならNone]
    # }
    def retry(self, job_id: str) -> str | None:
        with self._condition:
            source = self._records.get(job_id)
            if (
                source is None
                or source.state not in {"error", "failed", "cancelled", "interrupted"}
                or not source.retryable
                or not source.operation_id
                or not source.manifest_ref
            ):
                return None
            existing = next(
                (record.id for record in self._records.values() if record.retry_of == job_id),
                None,
            )
            if existing is not None:
                return existing
            handler = self._retry_handlers.get(source.kind)
            if handler is None or job_id in self._retry_inflight:
                return None
            self._retry_inflight.add(job_id)
            source_snapshot = self._snapshot_locked(source)
        try:
            retry_job_id = handler(source_snapshot)
        finally:
            with self._condition:
                self._retry_inflight.discard(job_id)
        with self._condition:
            retry_record = self._records.get(retry_job_id)
            if (
                retry_record is None
                or retry_record.retry_of != job_id
                or retry_record.operation_id != source_snapshot.operation_id
                or retry_record.manifest_ref != source_snapshot.manifest_ref
            ):
                raise ValueError(
                    "Retry handler must create a child with matching operation_id and retry_of"
                )
            return retry_job_id

    # {
    #   責務: [_restore_locked: persisted snapshotsを読み戻しactive Jobをinterruptedへ変換する]
    #   処理: [1: store snapshotsを読む 2: active stateを中断記録へ変換する 3: runtime recordへ再構築する]
    #   引数: []
    #   戻り値: []
    # }
    def _restore_locked(self) -> None:
        for snapshot in self._store.load():
            self._sequence += 1
            state = snapshot.state
            finished_at = snapshot.finished_at
            message = snapshot.message
            logs = snapshot.logs
            if state in ACTIVE_JOB_STATES and state != "paused":
                state = "interrupted"
                finished_at = time.time()
                message = "アプリ終了により中断しました。manifest/checkpointから再開できます"
                logs = (*logs, "recovered as interrupted")[-MAX_LOG_LINES:]
            values = dict(snapshot.__dict__)
            values.update(
                state=state,
                finished_at=finished_at,
                message=message,
                logs=deque(logs, maxlen=MAX_LOG_LINES),
            )
            record = _JobRecord(sequence=self._sequence, **values)
            self._records[record.id] = record
            self._cancel[record.id] = Event()
        self._trim_locked()
        self._persist_locked()

    # {
    #   責務: [_snapshot_locked: mutable recordからimmutable共有snapshotを作る]
    #   処理: [1: 現在のrecord fieldをJobSnapshotへコピーする]
    #   引数: [record: 変換対象の内部Job record]
    #   戻り値: [snapshot: immutable Job contract]
    # }
    @staticmethod
    def _snapshot_locked(record: _JobRecord) -> JobSnapshot:
        return JobSnapshot(
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
            record.cancel_capability,
            record.checkpoint_capability,
            record.checkpoint_ref,
            record.shutdown_policy,
            record.partial_result_policy,
            record.operation_id,
            record.manifest_ref,
            record.completed_items,
            record.pending_items,
            record.failed_items,
            record.artifact_refs,
        )

    # {
    #   責務: [_persist_locked: 現在のbounded Job historyをstoreへ保存する]
    #   処理: [1: sequence順にimmutable snapshotを作る 2: storeへatomic保存する]
    #   引数: []
    #   戻り値: []
    # }
    def _persist_locked(self) -> None:
        if self._store is not None:
            self._store.replace_all(self._snapshots_locked())

    # {
    #   責務: [_snapshots_locked: 新しいJob順のsnapshot tupleを作る]
    #   処理: [1: creation timestampとsequenceで降順sortする 2: immutable snapshotへ変換する]
    #   引数: []
    #   戻り値: [snapshots: Job snapshot tuple]
    # }
    def _snapshots_locked(self) -> tuple[JobSnapshot, ...]:
        records = sorted(
            self._records.values(),
            key=lambda item: (item.created_at, item.sequence),
            reverse=True,
        )
        return tuple(self._snapshot_locked(record) for record in records)

    # {
    #   責務: [_bounded_item_ids: item参照列を重複なしのbounded tupleへ正規化する]
    #   処理: [1: 文字列化する 2: 空値を除外する 3: 先頭10,000件へ制限する]
    #   引数: [values: itemまたはartifact参照列]
    #   戻り値: [items: 安全な参照tuple]
    # }
    @staticmethod
    def _bounded_item_ids(values) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(value)[:512] for value in values if value))[:10_000]
