"""One bounded IO operation at a time. No Tk calls or hidden job queue."""
import json
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from comfyui_support_tools.applications.main_gui.data.processing.tagger_transport import TaggerTransport
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionEvent


class ActionIO:
    def __init__(self, transport=None):
        self._transport = transport or TaggerTransport()
        self._events = Queue(maxsize=64)
        self._lock = Lock()
        self._cancel = Event()
        self._closed = False
        self._thread = None

    def start(self, request):
        with self._lock:
            if self._closed or (self._thread and self._thread.is_alive()):
                raise ValueError("Action実行中または終了済みです")
            if request.kind not in ("probe", "tag") or len(request.items) > 60:
                raise ValueError("Unsupported action request")
            self._cancel = Event()
            self._thread = Thread(target=self._run, args=(request,), daemon=True, name="inspector-action")
            self._thread.start()

    def _emit(self, event):
        while not self._closed:
            try:
                self._events.put(event, timeout=0.05)
                return
            except Full:
                continue

    def _run(self, request):
        try:
            if request.kind == "probe":
                models = self._transport.probe(request.settings)
                if not self._cancel.is_set():
                    self._emit(ActionEvent(request.token, "models", models=models))
            else:
                for item in request.items:
                    if self._cancel.is_set():
                        break
                    try:
                        payload = self._transport.tag(item, request.settings)
                        if self._cancel.is_set():
                            break
                        text = json.dumps(payload, allow_nan=False)
                        self._emit(ActionEvent(request.token, "result", item=item, message=text))
                    except Exception as exc:
                        self._emit(ActionEvent(request.token, "result", item=item,
                                               message=f"{type(exc).__name__}: {exc}"[:300], failed=True))
        except Exception as exc:
            self._emit(ActionEvent(request.token, "error", message=f"{type(exc).__name__}: {exc}"[:300], failed=True))
        finally:
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

    def close(self):
        self._closed = True
        self.cancel()
