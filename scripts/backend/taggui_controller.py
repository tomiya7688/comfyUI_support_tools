from ..context import *
from ..runtime_python import venv_python

# {
# 責務: [TagGUIController: TagGUIを画像フォルダ指定で起動・停止する]
# フィールド: [_process: 起動したTagGUI process, _lock: process参照を保護するlock]
# 処理: [1: 画像folderの妥当性を確認してGUIを起動する, 2: 起動processを終了する]
# }
class TagGUIController:
    """指定フォルダを読み込んだ状態でTagGUIを起動する。"""

    # {
    # 責務: [__init__: TagGUI process管理状態を初期化する]
    # 処理: [1: process参照と同期lockを用意する]
    # 引数: []
    # 戻り値: []
    # }
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()

    # {
    # 責務: [_write_log: log callbackがあればメッセージを渡す]
    # 処理: [1: callbackを安全に呼び出し、callback例外は無視する]
    # 引数: [log: 任意のlog callback, message: 表示する文字列]
    # 戻り値: []
    # }
    @staticmethod
    def _write_log(log, message):
        if log is not None:
            try:
                log(message)
            except Exception:
                pass

    # {
    # 責務: [start: 指定画像folderをTagGUIへ渡してGUI processを起動する]
    # 処理: [1: folder pathを正規化して存在を検査する, 2: process重複を防いでTagGUIを起動する,
    # 3: stdout監視と終了状態を管理する]
    # 引数: [image_directory: TagGUIで開く画像folder, log: 任意の状態通知callback]
    # 戻り値: []
    # }
    def start(self, image_directory, log=None):
        image_directory = Path(image_directory).expanduser().resolve()
        if not image_directory.is_dir():
            raise FileNotFoundError(f"画像フォルダがありません: {image_directory}")

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._write_log(
                    log,
                    "TagGUIは既に起動しています。TagGUI側の Load Directory で切り替えてください。",
                )
                return

            run_gui = TAGGUI_DIR / "taggui" / "run_gui.py"
            pythonw = venv_python(TAGGUI_DIR / "venv", windowed=True)
            python = venv_python(TAGGUI_DIR / "venv")
            if run_gui.is_file() and (pythonw.is_file() or python.is_file()):
                executable = pythonw if pythonw.is_file() else python
                command = [str(executable), str(run_gui), str(image_directory)]
                working_directory = TAGGUI_DIR
            elif TAGGUI_PACKAGED_EXE.is_file():
                command = [str(TAGGUI_PACKAGED_EXE), str(image_directory)]
                working_directory = TAGGUI_PACKAGED_EXE.parent
            else:
                raise FileNotFoundError(
                    f"TagGUIがありません: {run_gui} / {TAGGUI_PACKAGED_EXE}"
                )

            creationflags = 0x00000200 if os.name == "nt" else 0
            self._process = subprocess.Popen(
                command,
                cwd=str(working_directory),
                creationflags=creationflags,
            )
        self._write_log(log, f"✅ TagGUIを起動しました: {image_directory}")

    # {
    # 責務: [stop: 起動中のTagGUI processを終了する]
    # 処理: [1: process参照を解除する, 2: 未起動なら通知して戻る, 3: processへ終了要求を送る]
    # 引数: [log: 任意の状態通知callback]
    # 戻り値: []
    # }
    def stop(self, log=None):
        with self._lock:
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            self._write_log(log, "TagGUIは起動していません")
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._write_log(log, "TagGUIを停止しました")
