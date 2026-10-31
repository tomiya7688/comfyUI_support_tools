from ..context import *


# {
# 責務: [LogBox: 上限付きqueueを使ってbackground logをGUIに表示する]
# フィールド: [MAX_PENDING_LOGS: queue上限, MAX_RENDERED_LINES: 表示行数上限]
# }
class LogBox(ScrolledText):
    MAX_PENDING_LOGS = 2000
    MAX_RENDERED_LINES = 5000

    # {
    # 責務: [__init__: 上限付きログキューと表示widgetを初期化する]
    # 処理: [1: ScrolledTextを設定する, 2: pending log queueを作成する]
    # 引数: [self, master, kwargs]
    # 戻り値: []
    # }
    def __init__(self, master, **kwargs):
        super().__init__(master, wrap="word", height=16, **kwargs)
        self.configure(state="normal")
        self._pending_logs: "queue.Queue[str]" = queue.Queue(maxsize=self.MAX_PENDING_LOGS)
        self._flush_scheduled = False

    # {
    # 責務: [log: producer threadから安全にログをqueueへ追加する]
    # 処理: [1: queueが満杯なら古い要素を捨てて再試行する, 2: UI flushをscheduleする]
    # 引数: [self, msg]
    # 戻り値: []
    # }
    def log(self, msg: str) -> None:
        message = str(msg)
        while True:
            try:
                self._pending_logs.put_nowait(message)
                break
            except queue.Full:
                try:
                    self._pending_logs.get_nowait()
                except queue.Empty:
                    continue
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.after(0, self._flush_logs)

    # {
    # 責務: [_trim_visible_lines: 表示ログの最大行数を保つ]
    # 処理: [1: 上限を超えた古い行を先頭から削除する]
    # 引数: [self]
    # 戻り値: []
    # }
    def _trim_visible_lines(self) -> None:
        line_count = int(self.index("end-1c").split(".", 1)[0])
        excess = line_count - self.MAX_RENDERED_LINES
        if excess > 0:
            self.delete("1.0", f"{excess + 1}.0")

    # {
    # 責務: [_flush_logs: queue済みログをTk widgetに表示する]
    # 処理: [1: queueを空にする, 2: 表示行数を上限内に保つ]
    # 引数: [self]
    # 戻り値: []
    # }
    def _flush_logs(self) -> None:
        self._flush_scheduled = False
        while True:
            try:
                message = self._pending_logs.get_nowait()
            except queue.Empty:
                break
            self.insert("end", message + "\n")
        self._trim_visible_lines()
        self.see("end")
        self.update_idletasks()
