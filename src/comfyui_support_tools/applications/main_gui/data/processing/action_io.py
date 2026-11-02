"""Bounded Inspector Action worker integrated with the shared Job Runtime."""

import json
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.data.processing.result_exporter import (
    export_records,
)
from comfyui_support_tools.applications.main_gui.data.processing.tagger_transport import (
    TaggerTransport,
)
from comfyui_support_tools.shared.contracts.job_contracts import CheckpointCapability
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionEvent


class ActionIO:
    def __init__(self, transport=None, jobs=None):
        self._transport = transport or TaggerTransport()
        self._jobs_owned = jobs is None
        self._jobs = jobs or JobRuntime()
        self._events = Queue(maxsize=64)
        self._lock = Lock()
        self._cancel = Event()
        self._closed = False
        self._thread = None
        self.last_job_id = ""

    def start(self, request):
        with self._lock:
            if self._closed or (self._thread and self._thread.is_alive()):
                raise ValueError("Action実行中または終了済みです")
            if request.kind not in ("probe", "tag", "export") or len(request.items) > 60:
                raise ValueError("Unsupported action request")
            if request.kind == "export" and (
                request.export_settings is None or len(request.export_records) != len(request.items)
            ):
                raise ValueError("Invalid export request")
            self._cancel = Event()
            if request.kind == "probe":
                job_kind, action = "tagger_probe", "Tagger API 接続確認"
            elif request.kind == "tag":
                job_kind, action = "tagger_tag", f"Tag / 内容タグ付け ({len(request.items)}件)"
            else:
                job_kind, action = "analysis_export", f"Analysis Export ({len(request.items)}件)"
            self.last_job_id = self._jobs.create(
                job_kind,
                action,
                source_ids=tuple(item.id for item in request.items),
                source_names=tuple(item.name for item in request.items),
                cancel_event=self._cancel,
                checkpoint_capability=(
                    CheckpointCapability.ITEM
                    if request.kind in ("tag", "export")
                    else CheckpointCapability.NONE
                ),
            )
            self._thread = Thread(
                target=self._run,
                args=(request, self.last_job_id),
                daemon=True,
                name="inspector-action",
            )
            self._thread.start()

    def _emit(self, event):
        while not self._closed:
            try:
                self._events.put(event, timeout=0.05)
                return
            except Full:
                continue

    # {
    #   責務: [_run: Tagger/Export requestをshared Jobと協調cancel/pauseで実行する]
    #   処理: [1: Job slotを待つ 2: actionごとにbackend処理を行う 3: item境界を確認してterminal stateを記録する]
    #   引数: [request: immutable ActionRequest, job_id: shared Job ID]
    #   戻り値: []
    # }
    def _run(self, request, job_id):
        failed = False
        self._jobs.prepare(job_id)
        if not self._jobs.wait_start(job_id):
            self._emit(ActionEvent(request.token, "done", message="停止しました"))
            return
        try:
            if request.kind == "probe":
                self._jobs.update(job_id, 0.1, "モデル一覧を確認中", "GET /interrogators")
                models = self._transport.probe(request.settings)
                if not self._cancel.is_set():
                    self._emit(ActionEvent(request.token, "models", models=models))
                    self._jobs.update(
                        job_id, 0.9, f"モデル {len(models)}件を確認", "model list received"
                    )
            elif request.kind == "tag":
                total = len(request.items)
                completed = []
                failed_items = []
                for index, item in enumerate(request.items, 1):
                    if self._cancel.is_set() or self._jobs.finish_current_item_requested(job_id):
                        break
                    log = ""
                    try:
                        payload = self._transport.tag(item, request.settings)
                        if self._cancel.is_set():
                            break
                        text = json.dumps(payload, allow_nan=False)
                        self._emit(ActionEvent(request.token, "result", item=item, message=text))
                        log = f"{item.name}: response received"
                    except Exception as exc:
                        failed_items.append(item.id)
                        message = f"{type(exc).__name__}: {exc}"[:300]
                        self._emit(
                            ActionEvent(
                                request.token, "result", item=item, message=message, failed=True
                            )
                        )
                        log = f"{item.name}: {message}"[:400]
                    self._jobs.update(
                        job_id,
                        index / max(1, total),
                        f"{index}/{total} 処理済み",
                        log,
                    )
                    if not self._cancel.is_set():
                        completed.append(item.id)
                    can_continue = self._jobs.checkpoint(
                        job_id,
                        f"item:{index}",
                        completed_items=completed,
                        pending_items=(value.id for value in request.items[index:]),
                        failed_items=failed_items,
                    )
                    if not can_continue and not self._cancel.is_set():
                        if not self._jobs.wait_if_paused(job_id):
                            break
                    if self._jobs.finish_current_item_requested(job_id):
                        break
            else:

                def progress(index, total, name):
                    if self._cancel.is_set():
                        raise ValueError("Export停止要求を受信しました")
                    self._jobs.update(
                        job_id,
                        index / max(1, total),
                        f"{index}/{total} ファイル出力",
                        name,
                    )

                written = export_records(
                    request.export_records,
                    request.export_settings,
                    progress,
                )
                if not self._cancel.is_set():
                    self._emit(
                        ActionEvent(
                            request.token,
                            "exported",
                            message=f"Export完了: {len(written)}ファイル",
                        )
                    )
        except Exception as exc:
            if self._cancel.is_set():
                self._emit(ActionEvent(request.token, "done", message="停止しました"))
            else:
                failed = True
                message = f"{type(exc).__name__}: {exc}"[:300]
                self._emit(ActionEvent(request.token, "error", message=message, failed=True))
                self._jobs.finish(job_id, "error", f"{request.kind} エラー", message)
        finally:
            if self._cancel.is_set():
                self._jobs.finish(job_id, "cancelled", "停止しました")
            elif self._jobs.finish_current_item_requested(job_id):
                self._jobs.finish(job_id, "cancelled", "現在のitemまで完了して停止しました")
            elif not failed:
                self._jobs.finish(job_id, "done", "完了")
            self._emit(
                ActionEvent(
                    request.token,
                    "done",
                    message="停止しました" if self._cancel.is_set() else "完了",
                )
            )

    def poll(self):
        events = []
        for _ in range(64):
            try:
                events.append(self._events.get_nowait())
            except Empty:
                break
        return tuple(events)

    def cancel(self):
        self._cancel.set()
        if self.last_job_id:
            self._jobs.cancel(self.last_job_id)

    def close(self):
        self._closed = True
        self.cancel()
        if self._jobs_owned:
            self._jobs.close()
