import os

from ..context import *
from ..runtime_python import venv_python

# {
# 責務: [PixAITaggerServer: PixAI Tagger APIの既存接続確認とserver process管理を行う]
# フィールド: [_process: 起動したserver process, _lock: process参照を保護するlock]
# 処理: [1: API-only時は既存APIを利用する, 2: 必要な場合だけserverを起動しlogを転送する]
# }
class PixAITaggerServer:
    # {
    # 責務: [__init__: PixAI Tagger process管理状態を初期化する]
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
    # 責務: [_is_online: localhostのPixAI Tagger health endpointを確認する]
    # 処理: [1: requestsの有無を確認する, 2: 短いtimeoutでhealth APIを照会する]
    # 引数: []
    # 戻り値: [HTTP 200応答が得られた場合はTrue]
    # }
    def _is_online(self):
        if requests is None:
            return False
        try:
            response = requests.get("http://127.0.0.1:7861/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    # {
    # 責務: [_forward_output: server processの標準出力をlogへ転送して終了を反映する]
    # 処理: [1: process出力を行ごとに通知する, 2: 終了を待ち同じprocessなら参照を解除する]
    # 引数: [process: 出力を監視するserver process, log: 任意のlog callback]
    # 戻り値: []
    # }
    def _forward_output(self, process, log):
        if process.stdout is not None:
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    self._write_log(log, f"PixAI: {line}")
        return_code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
        self._write_log(log, f"PixAI Tagger API終了（コード: {return_code}）")

    # {
    # 責務: [start: 必要な場合にPixAI Tagger serverを起動する]
    # 処理: [1: API-only設定と既存APIを確認する, 2: 起動済みprocessを重複起動しない,
    # 3: serverを起動し標準出力監視threadを開始する]
    # 引数: [log: 任意の状態通知callback]
    # 戻り値: []
    # }
    def start(self, log=None):
        if API_ONLY_MODE:
            self._write_log(log, "API専用モードではPixAI Taggerを起動せず、設定済みAPIへ接続します")
            return
        if self._is_online():
            self._write_log(log, "✅ PixAI Tagger APIは既に起動しています")
            return
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._write_log(log, "PixAI Tagger APIは起動処理中です")
                return
            python_path = venv_python(PIXAI_TAGGER_DIR / ".venv")
            script_path = PIXAI_TAGGER_DIR / "api_server.py"
            if not python_path.is_file():
                raise FileNotFoundError(f"PixAI TaggerのPythonがありません: {python_path}")
            if not script_path.is_file():
                raise FileNotFoundError(f"PixAI Tagger APIがありません: {script_path}")
            creationflags = 0x00000200 if os.name == "nt" else 0
            environment = os.environ.copy()
            environment.setdefault("ONNX_MODE", "gpu")
            site_packages = python_path.parent.parent / "Lib" / "site-packages"
            nvidia_bin_dirs = [str(path) for path in (site_packages / "nvidia").glob("*/bin") if path.is_dir()]
            if nvidia_bin_dirs:
                environment["PATH"] = os.pathsep.join(nvidia_bin_dirs + [environment.get("PATH", "")])
            process = subprocess.Popen(
                [str(python_path), str(script_path), "--host", "127.0.0.1", "--port", "7861"],
                cwd=str(PIXAI_TAGGER_DIR),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            self._process = process
        threading.Thread(target=self._forward_output, args=(process, log), daemon=True).start()
        self._write_log(log, "🚀 PixAI Tagger APIを起動中: http://127.0.0.1:7861")
        for _ in range(60):
            if self._is_online():
                self._write_log(log, "✅ PixAI Tagger APIが起動しました")
                return
            if process.poll() is not None:
                raise RuntimeError(f"PixAI Tagger APIが終了しました（コード: {process.returncode}）")
            time.sleep(0.5)
        raise TimeoutError("PixAI Tagger APIが30秒以内に起動しませんでした")

    # {
    # 責務: [stop: このcontrollerが起動したPixAI Tagger processを終了する]
    # 処理: [1: process参照を取得する, 2: 未起動なら通知して戻る, 3: processを終了して参照を解除する]
    # 引数: [log: 任意の状態通知callback]
    # 戻り値: []
    # }
    def stop(self, log=None):
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            self._write_log(log, "PixAI Tagger APIはGUIから起動されていません")
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        with self._lock:
            if self._process is process:
                self._process = None
        self._write_log(log, "⏹️ PixAI Tagger APIを停止しました")
