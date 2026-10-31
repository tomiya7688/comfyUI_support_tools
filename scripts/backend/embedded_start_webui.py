from ..context import *
from ..runtime_python import venv_python


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
        self.launch_spec = create_configured_backend_launch_spec()
        self.DEFAULT_FLAGS = list(self.launch_spec.default_flags)
        self.API_URL = self.launch_spec.health_url
        self.PORT = self.launch_spec.port
        self.DISPLAY_NAME = self.launch_spec.display_name
        self._current_proc = None
        self._stop_event = threading.Event()
        self._health_check_stop = threading.Event()
        self._health_thread = None
        self._lifecycle_lock = threading.Lock()
        self._lifecycle_generation = 0
        self._lifecycle_active = False
        self._desired_running = False
        self._lifecycle_done = threading.Event()
        self._lifecycle_done.set()
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
            return {
                "status": "🟢 オンライン"
                if response.status_code == 200
                else f"🟡 HTTP {response.status_code}",
                "online": response.status_code == 200,
            }
        except requests.exceptions.Timeout:
            return {"status": "🟠 タイムアウト", "online": False}
        except requests.exceptions.ConnectionError:
            return {"status": "🔴 接続失敗", "online": False}
        except Exception as e:
            return {"status": f"❓ エラー: {str(e)[:30]}", "online": False}

    # {
    #   責務: [_health_check_thread: 実行中backendのhealth状態を更新する]
    #   処理: [1: stop eventまでAPI状態を調べる, 2: stop要求で速やかに終了する]
    #   引数: [self: backend状態を保持する起動管理, stop_event: この起動に属する停止event]
    #   戻り値: []
    # }
    def _health_check_thread(self, stop_event):
        while not stop_event.is_set():
            if self._current_proc is None:
                self._api_status = "⚫ オフライン"
            else:
                result = self._health_check_now()
                self._api_status = result["status"]
            if stop_event.wait(100):
                return

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
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                )
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
    def _start_webui_thread(
        self,
        flags,
        logical_cpu,
        ram_gb,
        low_prio,
        soft_stop_sec,
        hard_kill_sec,
        *,
        _generation=None,
    ):
        with self._lifecycle_lock:
            if _generation is None:
                if self._lifecycle_active or (
                    self._current_proc is not None and self._current_proc.poll() is None
                ):
                    self._log_msg(f"⚠️ {self.DISPLAY_NAME} は起動中です")
                    return
                self._lifecycle_generation += 1
                _generation = self._lifecycle_generation
                self._desired_running = True
            elif _generation != self._lifecycle_generation or not self._desired_running:
                return
            if self._lifecycle_active:
                return
            self._lifecycle_active = True
            self._lifecycle_done.clear()
            self._stop_event.clear()

        proc = None
        stop_event = threading.Event()
        health_thread = None
        try:
            python_path = venv_python(RUNTIME_DIR / "venv")
            launch_py = RUNTIME_DIR / self.launch_spec.launch_script_name
            if not launch_py.exists():
                self._log_msg(f"❌ 起動スクリプトが見つかりません: {launch_py}")
                return
            creationflags = 0x00000200 if os.name == "nt" else 0
            cmd = [str(python_path), str(launch_py)] + flags
            self._log_msg(f"🚀 起動中: {' '.join(cmd)}")
            with self._lifecycle_lock:
                if _generation != self._lifecycle_generation or not self._desired_running:
                    return
                proc = subprocess.Popen(cmd, cwd=str(RUNTIME_DIR), creationflags=creationflags)
                self._current_proc = proc
            previous_stop = self._health_check_stop
            previous_stop.set()
            previous_thread = self._health_thread
            if previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=4)
            health_thread = threading.Thread(
                target=self._health_check_thread, args=(stop_event,), daemon=True
            )
            self._health_check_stop = stop_event
            self._health_thread = health_thread
            health_thread.start()
            while proc.poll() is None and not self._stop_event.wait(0.25):
                pass
            if self._stop_event.is_set():
                self._stop_webui(soft_stop_sec, hard_kill_sec, proc)
            elif proc.poll() is not None:
                self._log_msg(f"⚠️ {self.DISPLAY_NAME} は終了しました (コード: {proc.returncode})")
        except Exception as error:
            self._log_msg(f"❌ {self.DISPLAY_NAME} の起動・監視に失敗しました: {error}")
            if proc is not None and proc.poll() is None:
                self._stop_webui(soft_stop_sec, hard_kill_sec, proc)
        finally:
            stop_event.set()
            if health_thread is not None:
                health_thread.join(timeout=4)
            if self._health_thread is health_thread:
                self._health_thread = None
            if self._current_proc is proc:
                self._current_proc = None
            with self._lifecycle_lock:
                self._lifecycle_active = False
                if _generation == self._lifecycle_generation:
                    self._desired_running = False
                self._lifecycle_done.set()

    # {
    #   責務: [_stop_webui: 子backendを猶予時間後に終了しreapする]
    #   処理: [1: CTRL_BREAKを送る, 2: terminate/killへ段階移行する, 3: waitで終了を回収する]
    #   引数: [self: backend表示名を持つ起動管理, soft_stop_sec: 通常停止待機秒, hard_kill_sec: 強制終了待機秒, proc: 停止対象process]
    #   戻り値: []
    # }
    def _stop_webui(self, soft_stop_sec, hard_kill_sec, proc=None):
        proc = proc or self._current_proc
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
        try:
            proc.wait(timeout=max(1.0, hard_kill_sec))
        except subprocess.TimeoutExpired:
            self._log_msg(f"⚠️ {self.DISPLAY_NAME} の終了確認がタイムアウトしました")

    # {
    #   責務: [_restart_webui: 連続したrestart要求を集約してbackendを再起動する]
    #   処理: [1: generationで古い要求を無効化する, 2: 既存lifecycle完了後に最新要求だけを起動する]
    #   引数: [self: lifecycle状態を持つ起動管理, args: backend起動引数]
    #   戻り値: []
    # }
    def _restart_webui(self, *args):
        with self._lifecycle_lock:
            self._lifecycle_generation += 1
            generation = self._lifecycle_generation
            self._desired_running = True
            self._stop_event.set()
            lifecycle_active = self._lifecycle_active
        if lifecycle_active and not self._lifecycle_done.wait(args[-2] + args[-1] + 5.0):
            with self._lifecycle_lock:
                if generation == self._lifecycle_generation:
                    self._desired_running = False
            self._log_msg(f"⚠️ {self.DISPLAY_NAME} の停止完了を待てず、再起動を保留しました")
            return
        with self._lifecycle_lock:
            if generation != self._lifecycle_generation or not self._desired_running:
                return
            if self._lifecycle_active:
                return
        self._start_webui_thread(*args, _generation=generation)

    # {
    #   責務: [request_stop: 開始中または実行中の起動要求を取り消す]
    #   処理: [1: generationを進めて保留中restartを無効化する, 2: 現在のlifecycleへ停止eventを送る]
    #   引数: [self: backend lifecycleを保持する起動管理]
    #   戻り値: []
    # }
    def request_stop(self):
        with self._lifecycle_lock:
            self._lifecycle_generation += 1
            self._desired_running = False
            self._stop_event.set()

    # {
    #   責務: [request_start: GUI起動workerより先に開始要求を予約する]
    #   処理: [1: 起動中や別の開始要求があれば拒否する, 2: generationを払い出して停止要求との競合を防ぐ]
    #   引数: [self: backend lifecycleを保持する起動管理]
    #   戻り値: [予約generation、開始できない場合はNone]
    # }
    def request_start(self):
        with self._lifecycle_lock:
            if self._lifecycle_active or self._desired_running:
                return None
            if self._current_proc is not None and self._current_proc.poll() is None:
                return None
            self._lifecycle_generation += 1
            self._desired_running = True
            self._stop_event.clear()
            return self._lifecycle_generation
