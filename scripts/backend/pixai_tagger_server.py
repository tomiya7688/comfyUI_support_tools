import os

from ..context import *
from ..runtime_python import venv_python

# {
#   責務: [PixAITaggerServer: PixAI Tagger API subprocess lifecycleを管理する]
#   処理: [health probe, process start, output forwarding and graceful shutdownを提供する]
#   フィールド: [process state and lock]
# }
# {
#   責務: [PixAITaggerServer: PixAI Tagger API subprocess lifecycleを管理する]
#   処理: [health probe, process start, output forwarding and graceful shutdownを提供する]
#   フィールド: [process state and lock]
# }
class PixAITaggerServer:
    # {
    #   責務: [__init__: server process state and synchronization lockを初期化する]
    #   処理: [empty process reference and thread lockを作る]
    #   引数: [self]
    #   戻り値: [None]
    # }
    # {
    #   責務: [__init__: server process state and synchronization lockを初期化する]
    #   処理: [empty process reference and thread lockを作る]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()

    # {
    #   責務: [_write_log: optional loggerへmessageを安全に送る]
    #   処理: [logger absence or logger exceptionsを無視する]
    #   引数: [log, message]
    #   戻り値: [None]
    # }
    # {
    #   責務: [_write_log: optional loggerへmessageを安全に送る]
    #   処理: [logger absence or logger exceptionsを無視する]
    #   引数: [log, message]
    #   戻り値: [None]
    # }
    @staticmethod
    def _write_log(log, message):
        if log is not None:
            try:
                log(message)
            except Exception:
                pass

    # {
    #   責務: [_is_online: local PixAI health endpointの応答を確認する]
    #   処理: [requests未導入、non-200 response, and request errorsをofflineとして扱う]
    #   引数: [self]
    #   戻り値: [bool]
    # }
    # {
    #   責務: [_is_online: local PixAI health endpointの応答を確認する]
    #   処理: [requests未導入、non-200 response, and request errorsをofflineとして扱う]
    #   引数: [self]
    #   戻り値: [bool]
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
    #   責務: [_forward_output: child stdoutをloggerへ転送しprocess終了を追跡する]
    #   処理: [output linesをprefix付きで記録し、終了後にmatching process stateをclearする]
    #   引数: [self, process, log]
    #   戻り値: [None]
    # }
    # {
    #   責務: [_forward_output: child stdoutをloggerへ転送しprocess終了を追跡する]
    #   処理: [output linesをprefix付きで記録し、終了後にmatching process stateをclearする]
    #   引数: [self, process, log]
    #   戻り値: [None]
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
    #   責務: [start: 必要時にPixAI Tagger APIを起動してready状態を待つ]
    #   処理: [API-only/current-process checks, venv validation, subprocess launch, health pollingを行う]
    #   引数: [self, log]
    #   戻り値: [None]
    # }
    # {
    #   責務: [start: 必要時にPixAI Tagger APIを起動してready状態を待つ]
    #   処理: [API-only/current-process checks, venv validation, subprocess launch, health pollingを行う]
    #   引数: [self, log]
    #   戻り値: [None]
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
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        with self._lock:
            if self._process is process:
                self._process = None
        raise TimeoutError("PixAI Tagger APIが30秒以内に起動しませんでした")

    # {
    #   責務: [stop: GUIが起動したPixAI Tagger processを終了する]
    #   処理: [terminateを試しtimeout時killし、process stateをclearする]
    #   引数: [self, log]
    #   戻り値: [None]
    # }
    # {
    #   責務: [stop: GUIが起動したPixAI Tagger processを終了する]
    #   処理: [terminateを試しtimeout時killし、process stateをclearする]
    #   引数: [self, log]
    #   戻り値: [None]
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
