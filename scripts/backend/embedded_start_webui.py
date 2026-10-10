from ..context import *
from ..runtime_python import venv_python
from .backend_launch_spec import create_backend_launch_spec

# {
#   責務: [EmbeddedStartWebUI: ローカル画像生成backendのプロセス起動と停止を管理する]
#   フィールド: [launch_spec: backend固有の起動設定, _current_proc: 起動中プロセス, _stop_event: 停止要求, _health_check_stop: health監視停止要求]
#   処理: [起動設定を共通化した上で, プロセス制御とAPIヘルス確認を行う]
# }
class EmbeddedStartWebUI:
    LOGICAL_TOTAL = 8
    LOGICAL_TO_USE = 4
    RAM_LIMIT_GB = None
    LOW_PRIORITY = True
    SOFT_STOP_WAIT_SEC = 4.0
    HARD_KILL_WAIT_SEC = 2.0
    # {
    #   責務: [__init__: 選択backendの起動設定とプロセス状態を初期化する]
    #   処理: [1: USER_PATHSからAPI URLを取得する, 2: 起動設定を作る, 3: プロセスと監視状態を初期化する]
    #   引数: [self: 初期化対象]
    #   戻り値: []
    # }
    def __init__(self):
        self.launch_spec = create_backend_launch_spec(
            RUNTIME_BACKEND,
            str(USER_PATHS.get("webui_api_url", "http://127.0.0.1:7860")),
            str(USER_PATHS.get("comfyui_api_url", "http://127.0.0.1:8188")),
            CHECKPOINTS_DIR,
            MODELS_DIR,
        )
        self.DEFAULT_FLAGS = list(self.launch_spec.default_flags)
        self.API_URL = self.launch_spec.health_url
        self.PORT = self.launch_spec.port
        self.DISPLAY_NAME = self.launch_spec.display_name
        self._current_proc = None
        self._stop_event = threading.Event()
        self._health_check_stop = threading.Event()
        self._api_status = "⚫ オフライン"
        self._log_msg = print

    # {
    #   責務: [_health_check_now: backend APIの応答状態を確認する]
    #   処理: [1: requestsの利用可否を確認する, 2: backend health URLへ問い合わせる, 3: 接続状態を返す]
    #   引数: [self: health URLを保持する起動管理]
    #   戻り値: [dict: status表示とonline状態]
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

    def _health_check_thread(self):
        while not self._health_check_stop.is_set():
            if self._current_proc is None:
                self._api_status = "⚫ オフライン"
            else:
                result = self._health_check_now()
                self._api_status = result["status"]
            time.sleep(100)

    # {
    #   責務: [_find_and_kill_webui_process: 指定ポートを待ち受ける外部プロセスを終了する]
    #   処理: [1: 未指定時は選択backendのportを使う, 2: WindowsのnetstatからPIDを調べる, 3: 対象PIDを終了する]
    #   引数: [self: portとログ出力先を持つ起動管理, port: 対象ポート]
    #   戻り値: [bool: プロセスを終了したか]
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
    #   責務: [_start_webui_thread: 選択backendのローカルプロセスを起動して終了まで監視する]
    #   処理: [1: 共通runtimeからPythonとbackend scriptを解決する, 2: processを起動する, 3: 停止要求または終了まで監視する]
    #   引数: [self: 起動設定と停止状態を持つ管理, flags: UIで指定された起動引数, logical_cpu: 使用CPU数, ram_gb: メモリ上限GB, low_prio: 低優先度設定, soft_stop_sec: 通常停止待機秒, hard_kill_sec: 強制終了待機秒]
    #   戻り値: []
    # }
    def _start_webui_thread(self, flags, logical_cpu, ram_gb, low_prio, soft_stop_sec, hard_kill_sec):
        python_path = venv_python(RUNTIME_DIR / "venv")
        launch_py = RUNTIME_DIR / self.launch_spec.launch_script_name
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
