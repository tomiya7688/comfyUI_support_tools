"""Bounded Inspector Action worker integrated with the shared Job Runtime."""
import json
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.data.processing.tagger_transport import TaggerTransport
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
            if request.kind not in ("probe", "tag") or len(request.items) > 60:
                raise ValueError("Unsupported action request")
            self._cancel = Event()
            action = "Tagger API 接続確認" if request.kind == "probe" else f"Tag / 内容タグ付け ({len(request.items)}件)"
            self.last_job_id = self._jobs.create(
                "tagger_probe" if request.kind == "probe" else "tagger_tag",
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

    def _emit(self, event):
        while not self._closed:
            try:
                self._events.put(event, timeout=0.05)
                return
            except Full:
                continue

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
                    self._jobs.update(job_id, 0.9, f"モデル {len(models)}件を確認", "model list received")
            else:
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
                        self._emit(ActionEvent(request.token, "result", item=item, message=message, failed=True))
                        log = f"{item.name}: {message}"[:400]
                    self._jobs.update(
                        job_id,
                        index / max(1, total),
                        f"{index}/{total} 処理済み",
                        log,
                    )
        except Exception as exc:
            failed = True
            message = f"{type(exc).__name__}: {exc}"[:300]
            self._emit(ActionEvent(request.token, "error", message=message, failed=True))
            self._jobs.finish(job_id, "error", "Tagger APIエラー", message)
        finally:
            if self._cancel.is_set():
                self._jobs.finish(job_id, "cancelled", "停止しました")
            elif not failed:
                self._jobs.finish(job_id, "done", "完了")
            self._emit(ActionEvent(request.token, "done", message="停止しました" if self._cancel.is_set() else "完了"))

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
