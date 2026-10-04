from ..context import *
from ..runtime_python import venv_python

# {
# 責務: [EmbeddedStartWebUI: Stable Diffusion backendの起動・停止と稼働状態を管理する]
# フィールド: [_current_proc: 起動したbackend process, _stop_event: 起動処理の停止通知,
# _health_check_stop: health check thread停止通知, _api_status: 表示用API状態, _log_msg: log callback]
# 処理: [1: API稼働状態を監視する, 2: backend processを起動・停止・再起動する]
# }
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

    # {
    # 責務: [__init__: process管理とhealth check用の初期状態を用意する]
    # 処理: [1: process参照、停止event、初期状態を設定する]
    # 引数: []
    # 戻り値: []
    # }
    def __init__(self):
        self._current_proc = None
        self._stop_event = threading.Event()
        self._health_check_stop = threading.Event()
        self._api_status = "⚫ オフライン"
        self._log_msg = print

    # {
    # 責務: [_health_check_now: 現在のbackend APIへ一度接続して状態を返す]
    # 処理: [1: requestsの有無を確認する, 2: APIへtimeout付きGETを送り結果を状態辞書にする]
    # 引数: []
    # 戻り値: [status表示文字列とonlineフラグを含む辞書]
    # }
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

    # {
    # 責務: [_health_check_thread: 停止指示までbackend API状態を周期確認する]
    # 処理: [1: processとAPI状態を確認する, 2: 表示状態を更新して次の確認を待つ]
    # 引数: []
    # 戻り値: []
    # }
    def _health_check_thread(self):
        while not self._health_check_stop.is_set():
            if self._current_proc is None:
                self._api_status = "⚫ オフライン"
            else:
                result = self._health_check_now()
                self._api_status = result["status"]
            time.sleep(100)

    # {
    # 責務: [_find_and_kill_webui_process: 指定portを占有する既存WebUI processを終了する]
    # 処理: [1: OSからport利用中processを特定する, 2: 終了を要求し結果を返す]
    # 引数: [port: 検索するAPI port、省略時は既定port]
    # 戻り値: [対象processを終了できた場合はTrue]
    # }
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

    # {
    # 責務: [_start_webui_thread: backend起動引数を組み立ててprocessを開始する]
    # 処理: [1: venvとbackend entrypointを解決する, 2: 低負荷・資源制限設定を引数化する,
    # 3: 起動processと監視状態を保持する]
    # 引数: [flags: 起動追加引数, logical_cpu: CPU設定, ram_gb: RAM設定, low_prio: 低優先度指定,
    # soft_stop_sec: graceful stop待ち時間, hard_kill_sec: 強制終了までの待ち時間]
    # 戻り値: []
    # }
    def _start_webui_thread(self, flags, logical_cpu, ram_gb, low_prio, soft_stop_sec, hard_kill_sec):
        python_path = venv_python(RUNTIME_DIR / "venv")
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

    # {
    # 責務: [_stop_webui: 起動中backendをgraceful stop後に必要なら強制終了する]
    # 処理: [1: soft stop signalを送る, 2: 指定時間待つ, 3: 残存時は強制終了する]
    # 引数: [soft_stop_sec: 正常終了を待つ秒数, hard_kill_sec: 強制終了後の待ち時間]
    # 戻り値: []
    # }
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

    # {
    # 責務: [_restart_webui: 既存backendを停止して同じ設定で起動し直す]
    # 処理: [1: health check停止を通知する, 2: 既存processを停止する, 3: 引数を使って再起動する]
    # 引数: [args: _start_webui_threadへ渡す起動・停止設定]
    # 戻り値: []
    # }
    def _restart_webui(self, *args):
        self._stop_event.set()
        self._stop_webui(args[-2], args[-1])
        self._start_webui_thread(*args)
