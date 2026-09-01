from ..context import *

class EmbeddedStartWebUI:
    DEFAULT_FLAGS = (
        ["--listen", "127.0.0.1", "--port", "8188", "--lowvram", "--disable-auto-launch"]
        if RUNTIME_BACKEND == "comfyui"
        else [
            "--lowvram", "--disable-safe-unpickle", "--api",
            "--ckpt-dir", str(CHECKPOINTS_DIR),
            "--lora-dir", str(MODELS_DIR / "Lora"),
            "--vae-dir", str(MODELS_DIR / "VAE"),
            "--embeddings-dir", str(MODELS_DIR / "embeddings"),
            "--hypernetwork-dir", str(MODELS_DIR / "hypernetworks"),
            "--esrgan-models-path", str(MODELS_DIR / "RealESRGAN"),
            "--gfpgan-models-path", str(MODELS_DIR / "GFPGAN"),
            "--codeformer-models-path", str(MODELS_DIR / "Codeformer"),
        ]
    )
    LOGICAL_TOTAL = 8
    LOGICAL_TO_USE = 4
    RAM_LIMIT_GB = None
    LOW_PRIORITY = True
    SOFT_STOP_WAIT_SEC = 4.0
    HARD_KILL_WAIT_SEC = 2.0
    API_URL = (
        "http://127.0.0.1:8188/system_stats"
        if RUNTIME_BACKEND == "comfyui"
        else "http://127.0.0.1:7860/sdapi/v1/progress"
    )
    PORT = 8188 if RUNTIME_BACKEND == "comfyui" else 7860
    DISPLAY_NAME = BACKEND_DISPLAY_NAME

    def __init__(self):
        self._current_proc = None
        self._stop_event = threading.Event()
        self._health_check_stop = threading.Event()
        self._api_status = "⚫ オフライン"
        self._log_msg = print

    def _health_check_now(self):
        if requests is None:
            return {"status": "❓ requests 未インストール", "online": False}
        try:
            response = requests.get(self.API_URL, timeout=3)
            return {"status": "🟢 オンライン" if response.status_code == 200 else f"🟡 HTTP {response.status_code}", "online": response.status_code == 200}
        except requests.exceptions.Timeout:
            return {"status": "🟠 タイムアウト", "online": False}
        except requests.exceptions.ConnectionError:
            return {"status": "🔴 接続失敗", "online": False}
        except Exception as e:
            return {"status": f"❓ エラー: {str(e)[:30]}", "online": False}

    def _health_check_thread(self):
        while not self._health_check_stop.is_set():
            if self._current_proc is None:
                self._api_status = "⚫ オフライン"
            else:
                result = self._health_check_now()
                self._api_status = result["status"]
            time.sleep(100)

    def _find_and_kill_webui_process(self, port=None):
        port = port or self.PORT
        try:
            if os.name == "nt":
                result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
                for line in result.stdout.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        pid = int(line.split()[-1])
                        subprocess.run(f"taskkill /PID {pid} /F", shell=True, check=False)
                        self._log_msg(f"💀 PID {pid} を強制終了しました")
                        return True
            self._log_msg(f"⚠️ ポート {port} を使用しているプロセスが見つかりません")
        except Exception as e:
            self._log_msg(f"❌ プロセス検出エラー: {e}")
        return False

    def _start_webui_thread(self, flags, logical_cpu, ram_gb, low_prio, soft_stop_sec, hard_kill_sec):
        python_path = RUNTIME_DIR / "venv" / "Scripts" / "python.exe"
        if not python_path.exists():
            python_path = Path(sys.executable)
        launch_py = RUNTIME_DIR / ("main.py" if RUNTIME_BACKEND == "comfyui" else "launch.py")
        if not launch_py.exists():
            self._log_msg(f"❌ 起動スクリプトが見つかりません: {launch_py}")
            return
        creationflags = 0x00000200 if os.name == "nt" else 0
        self._stop_event.clear()
        cmd = [str(python_path), str(launch_py)] + flags
        self._log_msg(f"🚀 起動中: {' '.join(cmd)}")
        self._current_proc = subprocess.Popen(cmd, cwd=str(RUNTIME_DIR), creationflags=creationflags)
        self._health_check_stop.clear()
        threading.Thread(target=self._health_check_thread, daemon=True).start()
        while self._current_proc and self._current_proc.poll() is None and not self._stop_event.is_set():
            time.sleep(0.25)
        if self._stop_event.is_set():
            self._stop_webui(soft_stop_sec, hard_kill_sec)
        elif self._current_proc:
            self._log_msg(f"⚠️ {self.DISPLAY_NAME} は終了しました (コード: {self._current_proc.returncode})")
        self._health_check_stop.set()
        self._current_proc = None

    def _stop_webui(self, soft_stop_sec, hard_kill_sec):
        proc = self._current_proc
        if not proc:
            return
        if os.name == "nt":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                pass
        deadline = time.time() + soft_stop_sec
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            proc.terminate()
        deadline = time.time() + hard_kill_sec
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            proc.kill()

    def _restart_webui(self, *args):
        self._stop_event.set()
        self._stop_webui(args[-2], args[-1])
        self._start_webui_thread(*args)
