"""Bounded media IO; scans participate in the shared Job Runtime.

One scan worker and one preview decoder are retained. Scan work obtains a
global Job slot; preview decoding is short-lived UI support and is not a Job.
"""

from collections import deque
from queue import Empty, Full, Queue
from threading import Condition, Event, Thread

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.data.processing.media_scan import scan_folder
from comfyui_support_tools.applications.main_gui.data.processing.media_preview_reader import (
    MediaPreviewReader,
)
from comfyui_support_tools.shared.contracts.media_event import MediaEvent


# {
# 責務: [MediaIO: bounded scan/preview workerを管理しscanをshared Job runtimeへ参加させる]
# フィールド: [JobRuntime ownership, condition/cancel state, pending requests, tokenized bounded event queues, worker threads]
# }
class MediaIO:
    # {
    #   責務: [__init__: shared job runtimeとbounded media request/event stateを初期化する]
    #   処理: [runtimeがなければ所有runtimeを作り、scan/preview queuesとworker stateを設定する]
    #   引数: [self: IO adapter, jobs: optional shared JobRuntime]
    #   戻り値: [なし]
    # }
    def __init__(self, jobs=None):
        self._jobs_owned = jobs is None
        self._jobs = jobs or JobRuntime()
        self._condition = Condition()
        self._stop = Event()
        self._cancel = Event()
        self._scan_request = None
        self._scan_job_id = ""
        self._thumbnails = deque()
        self._preview = None
        self._token = 0
        self._scan_events = Queue(maxsize=8)
        self._preview_events = Queue(maxsize=72)
        self._threads = []

    # {
    #   責務: [_start_workers: scanとpreviewのsingle daemon workerを必要時に起動する]
    #   処理: [closed stateを拒否しthread listが空の場合のみ2 threadを開始する]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   エラー: [RuntimeError: MediaIOがclose済み]
    #   副作用: [media-scan/media-preview workerをspawnする]
    # }
    def _start_workers(self):
        if self._stop.is_set():
            raise RuntimeError("Media Browser is closed")
        if not self._threads:
            self._threads = [
                Thread(target=self._scan_loop, daemon=True, name="media-scan"),
                Thread(target=self._preview_loop, daemon=True, name="media-preview"),
            ]
            for thread in self._threads:
                thread.start()

    # {
    #   責務: [scan: 現在scanをcancelし新token/job付きfolder scanをenqueueする]
    #   処理: [worker起動、前job cancel、token increment、新job作成、pending previewをclearする]
    #   引数: [self: IO adapter, folder: scan root, collection: collection label]
    #   戻り値: [int: 新しいview generation token]
    #   副作用: [scan jobとpending request queueを更新する]
    # }
    def scan(self, folder, collection):
        with self._condition:
            self._start_workers()
            self._cancel.set()
            if self._scan_job_id:
                self._jobs.cancel(self._scan_job_id)
            self._cancel = Event()
            self._token += 1
            self._scan_job_id = self._jobs.create(
                "media_scan",
                f"Media Scan ({collection})",
                source_names=(str(folder),),
                cancel_event=self._cancel,
            )
            self._scan_request = (folder, collection, self._token, self._cancel, self._scan_job_id)
            self._thumbnails.clear()
            self._preview = None
            self._condition.notify_all()
            return self._token

    # {
    #   責務: [thumbnails: 最大60 itemの128px preview batchをpending queueに置く]
    #   処理: [worker起動後、古いthumbnail requestsを新しいbatchに置換する]
    #   引数: [self: IO adapter, token: view generation token, items: MediaItem sequence]
    #   戻り値: [なし]
    #   副作用: [preview workerへthumbnail requestsを通知する]
    # }
    def thumbnails(self, token, items):
        with self._condition:
            self._start_workers()
            self._thumbnails = deque(("thumbnail", token, item, 128, 0.0) for item in items[:60])
            self._condition.notify_all()

    # {
    #   責務: [preview: itemとseek fractionの480px preview requestをpendingにする]
    #   処理: [current standalone previewを置換しdecoder workerをwakeする]
    #   引数: [self: IO adapter, token: view generation token, item: MediaItem, fraction: seek fraction]
    #   戻り値: [なし]
    #   副作用: [preview workerにrequestを通知する]
    # }
    def preview(self, token, item, fraction):
        with self._condition:
            self._start_workers()
            self._preview = ("preview", token, item, 480, fraction)
            self._condition.notify_all()

    # {
    #   責務: [_scan_loop: scan requestsを直列実行してprogress/result eventをownerへ送る]
    #   処理: [condition wait、Job slot取得、scan_folder実行、terminal/cancel状態のjob記録を行う]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   副作用: [scanner/JobRuntime/event queueを更新する]
    # }
    def _scan_loop(self):
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._scan_request is not None or self._stop.is_set()
                )
                if self._stop.is_set():
                    return
                request, self._scan_request = self._scan_request, None
            folder, collection, token, cancel, job_id = request
            if not self._jobs.wait_start(job_id):
                self._put(
                    self._scan_events,
                    MediaEvent("error", token, message="読込を停止しました"),
                    self._stop,
                )
                continue
            count = 0
            terminal = False

            # {
            #   責務: [publish: scan batch countでjob progressを更新しeventをbounded queueへ送る]
            #   処理: [batchは検出数、done/errorはterminal job statusに反映し、eventをenqueueする]
            #   引数: [event: scan_folderが生成するMediaEvent]
            #   戻り値: [なし]
            #   副作用: [closure count/terminal、JobRuntime、scan event queueを更新する]
            # }
            def publish(event):
                nonlocal count, terminal
                if event.kind == "batch":
                    count += len(event.items)
                    self._jobs.update(
                        job_id, None, f"{count:,}件を検出", f"found {count:,} media items"
                    )
                elif event.kind == "done":
                    terminal = True
                    self._jobs.finish(job_id, "done", event.message)
                elif event.kind == "error":
                    terminal = True
                    self._jobs.finish(job_id, "error", "Media Scanエラー", event.message)
                self._put(self._scan_events, event, cancel)

            scan_folder(folder, collection, token, cancel, publish)
            if cancel.is_set() and not terminal:
                self._jobs.finish(job_id, "cancelled", "Media Scanを停止しました")
                self._put(
                    self._scan_events,
                    MediaEvent("error", token, message="読込を停止しました"),
                    self._stop,
                )
            elif not terminal:
                self._jobs.finish(job_id, "error", "Media Scanが終端結果なしで終了しました")
                self._put(
                    self._scan_events,
                    MediaEvent("error", token, message="Media Scanが予期せず終了しました"),
                    self._stop,
                )

    # {
    #   責務: [_preview_loop: prioritized previewまたはthumbnail requestを順次decodeする]
    #   処理: [pending previewを先に取りreaderでdecodeしtokenized MediaEventを送る]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   副作用: [MediaPreviewReaderを利用してpreview eventを生成する]
    # }
    def _preview_loop(self):
        reader = MediaPreviewReader()
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._preview or self._thumbnails or self._stop.is_set()
                )
                if self._stop.is_set():
                    return
                if self._preview:
                    request, self._preview = self._preview, None
                else:
                    request = self._thumbnails.popleft()
            kind, token, item, edge, fraction = request
            result = reader.read(item, edge, fraction)
            self._put(self._preview_events, MediaEvent(kind, token, preview=result), self._stop)

    # {
    #   責務: [_put: cancel/closeされるまでbounded event queueへのputを再試行する]
    #   処理: [Full時は50ms待ってretryし、cancel/stop時は終了する]
    #   引数: [self: IO adapter, queue: target Queue, event: MediaEvent, cancel: request Event]
    #   戻り値: [なし]
    #   副作用: [queueへeventを書き込む]
    # }
    def _put(self, queue, event, cancel):
        while not cancel.is_set() and not self._stop.is_set():
            try:
                queue.put(event, timeout=0.05)
                return
            except Full:
                continue

    # {
    #   責務: [poll: scan queueから8件、preview queueから72件までnonblocking drainする]
    #   処理: [Emptyまでeventを回収しtupleとして返す]
    #   引数: [self: IO adapter]
    #   戻り値: [MediaEvent tuple]
    # }
    def poll(self):
        events = []
        for queue, limit in ((self._scan_events, 8), (self._preview_events, 72)):
            for _ in range(limit):
                try:
                    events.append(queue.get_nowait())
                except Empty:
                    break
        return tuple(events)

    # {
    #   責務: [close: scan/preview worker stateを停止し所有runtimeだけを閉じる]
    #   処理: [stop/cancelをset、scan cancel、pending work clear、waiter notifyを行う]
    #   引数: [self: IO adapter]
    #   戻り値: [なし]
    #   副作用: [worker shutdownを通知し必要時はJobRuntimeをcloseする]
    # }
    def close(self):
        with self._condition:
            self._stop.set()
            self._cancel.set()
            if self._scan_job_id:
                self._jobs.cancel(self._scan_job_id)
            self._scan_request = None
            self._thumbnails.clear()
            self._preview = None
            self._condition.notify_all()
        if self._jobs_owned:
            self._jobs.close()
