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
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionEvent


# {
# 責務: [ActionIO: Inspector probe/tag/exportをbounded workerとshared Job runtimeで実行する]
# フィールド: [_transport, _jobs, bounded event queue, worker/cancel/closed state, last_job_id]
# }
class ActionIO:
    # {
    #   責務: [__init__: transport/runtimeとbounded event/worker stateを初期化する]
    #   処理: [外部runtimeがなければ所有runtimeを作り、64 event queueとlock/cancel stateを用意する]
    #   引数: [self: IO adapter, transport: optional TaggerTransport, jobs: optional shared JobRuntime]
    #   戻り値: [なし]
    # }
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

    # {
    #   責務: [start: 検証済みInspector actionをJob runtimeとbackground workerへ登録する]
    #   処理: [request種別/件数/export inputを検証し、jobを作成して一つのworkerを開始する]
    #   引数: [self: IO adapter, request: token付きActionRequest]
    #   戻り値: [なし]
    #   エラー: [ValueError: closed/running状態、unsupported kind、または不正なrequest]
    #   副作用: [JobSnapshotを追加しdaemon worker threadを開始する]
    # }
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
            )
            self._thread = Thread(
                target=self._run,
                args=(request, self.last_job_id),
                daemon=True,
                name="inspector-action",
            )
            self._thread.start()

    # {
    #   責務: [_emit: eventをbounded queueへ追加し、満杯ならcloseまでbackpressureする]
    #   処理: [50ms timeoutでqueue.putを再試行する]
    #   引数: [self: IO adapter, event: ownerへ返すActionEvent]
    #   戻り値: [なし]
    #   副作用: [event queueへ書き込む]
    # }
    def _emit(self, event):
        while not self._closed:
            try:
                self._events.put(event, timeout=0.05)
                return
            except Full:
                continue

    # {
    #   責務: [_run: probe/tag/exportを実行しprogress/result/error/terminal eventを送る]
    #   処理: [Job slotを待ち、request kind別にtransport/exporterを呼び、cancel/failureをterminal stateへ反映する]
    #   引数: [self: IO adapter, request: ActionRequest, job_id: shared job ID]
    #   戻り値: [なし]
    #   副作用: [HTTP Tagger、filesystem export、JobRuntime、event queueを更新する]
    # }
    def _run(self, request, job_id):
        failed = False
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
                for index, item in enumerate(request.items, 1):
                    if self._cancel.is_set():
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
            else:
                # {
                #   責務: [progress: export中にcancelを確認しjob progressとfile名を記録する]
                #   処理: [cancel時はValueErrorでexportを中断し、通常時はfraction/message/logを更新する]
                #   引数: [index: 完了数, total: export対象数, name: 現在のfile名]
                #   戻り値: [なし]
                #   エラー: [ValueError: export停止要求を受け取った]
                # }
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
            elif not failed:
                self._jobs.finish(job_id, "done", "完了")
            self._emit(
                ActionEvent(
                    request.token,
                    "done",
                    message="停止しました" if self._cancel.is_set() else "完了",
                )
            )

    # {
    #   責務: [poll: bounded event queueから最大64件の完了eventをdrainする]
    #   処理: [Emptyまでnonblocking getしtupleとして返す]
    #   引数: [self: IO adapter]
    #   戻り値: [ActionEvent tuple]
    # }
    def poll(self):
        events = []
        for _ in range(64):
            try:
                events.append(self._events.get_nowait())
            except Empty:
                break
        return tuple(events)

    # {
    #   責務: [cancel: current request cancellation eventをsetしjob cancelを通知する]
    #   処理: [eventをsetしlast_job_idがあればruntime.cancelを呼ぶ]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   副作用: [workerへcancel signalを送りjob stateを更新する]
    # }
    def cancel(self):
        self._cancel.set()
        if self.last_job_id:
            self._jobs.cancel(self.last_job_id)

    # {
    #   責務: [close: adapterをclosedにしactive actionをcancelする]
    #   処理: [queue producerを止めcancelし、adapter所有runtimeだけを閉じる]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   副作用: [worker/runtime lifecycleへ停止を通知する]
    # }
    def close(self):
        self._closed = True
        self.cancel()
        if self._jobs_owned:
            self._jobs.close()
