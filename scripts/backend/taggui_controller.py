from ..context import *
from ..runtime_python import venv_python

# TagGUI's Transformers import can reach torchvision before PyTorch is initialized.
TAGGUI_BOOTSTRAP_CODE = """
import importlib
import runpy
import sys
from pathlib import Path

run_gui = Path(sys.argv[1]).resolve()
image_directory = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(run_gui.parent))
importlib.import_module("torch")
sys.argv = [str(run_gui), str(image_directory)]
runpy.run_path(str(run_gui), run_name="__main__")
"""


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

    # {
    #   責務: [start: 選択フォルダを渡してTagGUIを起動する]
    #   処理: [1: 入力画像フォルダを検証する, 2: 既存の起動状態を確認する, 3: PyTorchを先に初期化するbootstrapでTagGUIを起動する]
    #   引数: [image_directory: TagGUIへ渡す画像フォルダ, log: 起動結果を受け取る任意logger]
    #   戻り値: []
    #   エラー: [FileNotFoundError: 画像フォルダまたはTagGUIがない場合]
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
                command = [
                    str(executable),
                    "-c",
                    TAGGUI_BOOTSTRAP_CODE,
                    str(run_gui),
                    str(image_directory),
                ]
                working_directory = TAGGUI_DIR
            elif TAGGUI_PACKAGED_EXE.is_file():
                command = [str(TAGGUI_PACKAGED_EXE), str(image_directory)]
                working_directory = TAGGUI_PACKAGED_EXE.parent
            else:
                raise FileNotFoundError(f"TagGUIがありません: {run_gui} / {TAGGUI_PACKAGED_EXE}")

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
