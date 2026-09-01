from ..context import *

class PixAITaggerServer:
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

    def _is_online(self):
        if requests is None:
            return False
        try:
            response = requests.get("http://127.0.0.1:7861/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

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

    def start(self, log=None):
        if self._is_online():
            self._write_log(log, "✅ PixAI Tagger APIは既に起動しています")
            return
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._write_log(log, "PixAI Tagger APIは起動処理中です")
                return
            python_path = PIXAI_TAGGER_DIR / ".venv" / "Scripts" / "python.exe"
            script_path = PIXAI_TAGGER_DIR / "api_server.py"
            if not python_path.is_file():
                raise FileNotFoundError(f"PixAI TaggerのPythonがありません: {python_path}")
            if not script_path.is_file():
                raise FileNotFoundError(f"PixAI Tagger APIがありません: {script_path}")
            creationflags = 0x00000200 if os.name == "nt" else 0
            process = subprocess.Popen(
                [str(python_path), str(script_path), "--host", "127.0.0.1", "--port", "7861"],
                cwd=str(PIXAI_TAGGER_DIR),
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
