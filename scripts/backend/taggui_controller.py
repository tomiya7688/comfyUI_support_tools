from ..context import *
from ..subapp_runtime import packaged_executable

class TagGUIController:
    """指定フォルダを読み込んだ状態でTagGUIを起動する。"""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()

    @staticmethod
    def _write_log(log, message):
        if log is not None:
            try:
                log(message)
            except Exception:
                pass

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

            executable = TAGGUI_PACKAGED_EXE if TAGGUI_PACKAGED_EXE.is_file() else packaged_executable("taggui")
            if not executable.is_file():
                raise FileNotFoundError(f"同梱TagGUIが未導入です: {executable}")
            command = [str(executable), str(image_directory)]
            working_directory = executable.parent

            creationflags = 0x00000200 if os.name == "nt" else 0
            self._process = subprocess.Popen(
                command,
                cwd=str(working_directory),
                creationflags=creationflags,
            )
        self._write_log(log, f"✅ TagGUIを起動しました: {image_directory}")

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
