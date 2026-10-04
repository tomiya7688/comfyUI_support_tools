from ..context import *

# {
#   "責務": "thread-safeにmessageを受け取りTk event loop上で追記するlog widget。",
#   "フィールド": ["_pending_logs: 待機message queue", "_flush_scheduled: flush予約状態"]
# }
class LogBox(ScrolledText):
    # {
    #   "責務": "ScrolledText log widgetとflush queue状態を初期化する。",
    #   "処理": ["wrap/heightなどの基底widget optionを設定する", "queueとscheduled flagを初期化する"],
    #   "引数": {"master": "親widget", "kwargs": "ScrolledText option"}, "戻り値": []
    # }
    def __init__(self, master, **kwargs):
        super().__init__(master, wrap="word", height=16, **kwargs)
        self.configure(state="normal")
        self._pending_logs: "queue.Queue[str]" = queue.Queue()
        self._flush_scheduled = False

    # {
    #   "責務": "messageをqueueへ追加し必要に応じてUI flushを予約する。",
    #   "処理": ["文字列化したmessageをenqueueする", "flush未予約ならafter callbackを一つ登録する"],
    #   "引数": {"msg": "追加するlog message"}, "戻り値": []
    # }
    def log(self, msg: str) -> None:
        self._pending_logs.put(str(msg))
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.after(0, self._flush_logs)

    # {
    #   "責務": "待機logをText widgetへ追記し末尾を表示する。",
    #   "処理": ["scheduled flagを解除する", "queueを空にするまで追記し末尾へscrollする"],
    #   "引数": [], "戻り値": []
    # }
    def _flush_logs(self) -> None:
        self._flush_scheduled = False
        while not self._pending_logs.empty():
            self.insert("end", self._pending_logs.get() + "\n")
        self.see("end")
        self.update_idletasks()
