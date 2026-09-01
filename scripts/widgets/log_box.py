from ..context import *

class LogBox(ScrolledText):
    def __init__(self, master, **kwargs):
        super().__init__(master, wrap="word", height=16, **kwargs)
        self.configure(state="normal")
        self._pending_logs: "queue.Queue[str]" = queue.Queue()
        self._flush_scheduled = False

    def log(self, msg: str) -> None:
        self._pending_logs.put(str(msg))
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.after(0, self._flush_logs)

    def _flush_logs(self) -> None:
        self._flush_scheduled = False
        while not self._pending_logs.empty():
            self.insert("end", self._pending_logs.get() + "\n")
        self.see("end")
        self.update_idletasks()
