from ..context import *

class LogBox(ScrolledText):
    MAX_PENDING_LOGS = 2048
    MAX_TEXT_LINES = 5000

    def __init__(self, master, **kwargs):
        super().__init__(master, wrap="word", height=16, **kwargs)
        self.configure(state="normal")
        self._pending_logs: "queue.Queue[str]" = queue.Queue(maxsize=self.MAX_PENDING_LOGS)
        self._flush_scheduled = False

    def log(self, msg: str) -> None:
        message = str(msg)
        try:
            self._pending_logs.put_nowait(message)
        except queue.Full:
            try:
                self._pending_logs.get_nowait()
            except queue.Empty:
                pass
            self._pending_logs.put_nowait(message)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.after(0, self._flush_logs)

    def _trim_visible_lines(self) -> None:
        line_count = int(self.index("end-1c").split(".", 1)[0])
        excess = line_count - self.MAX_TEXT_LINES
        if excess > 0:
            self.delete("1.0", f"{excess + 1}.0")

    def _flush_logs(self) -> None:
        self._flush_scheduled = False
        while not self._pending_logs.empty():
            self.insert("end", self._pending_logs.get() + "\n")
        self._trim_visible_lines()
        self.see("end")
        self.update_idletasks()
