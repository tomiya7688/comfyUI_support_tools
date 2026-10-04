from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore
from ..subapp_runtime import launch_packaged_executable, packaged_executable

# {
#   "責務": "WebUI/ComfyUI backendの起動・停止・health確認を操作する。",
#   "フィールド": ["backend paths/commands: 起動対象", "process/process_lock: process制御", "status variables: backend状態", "preset_store: 起動設定保存", "logbox: 出力"]
# }
class StartWebUITab(ttk.Frame):
    # {
    #   "責務": "backend起動タブの設定、process状態、UIを初期化する。",
    #   "処理": ["backend設定と状態変数を初期化する", "defaultsを読み込み操作UIを構築する"],
    #   "引数": {"master": "親Tk widget"}, "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.mod = EMBEDDED_START_WEBUI
        self.preset_store = PresetStore("start_webui")
        self.preset_name = tk.StringVar()
        self.cpu = tk.StringVar(value="4")
        self.logical_total = tk.StringVar(value="8")
        self.ram = tk.StringVar(value="")
        self.low_priority = tk.BooleanVar(value=True)
        self.soft_stop = tk.StringVar(value="4.0")
        self.hard_kill = tk.StringVar(value="2.0")
        self.flags_text: tk.Text | None = None
        self.logbox: LogBox | None = None
        self._build()
        self._load_defaults()
        self.after(500, self._poll_status)

    # {
    #   "責務": "backend選択、起動設定、状態、操作ボタンとlog UIを構築する。",
    #   "処理": ["起動設定入力を配置する", "start/stop/health/restart操作とlogを配置する"],
    #   "引数": [], "戻り値": []
    # }
    def _build(self):
        if isinstance(self.mod, Exception):
            ttk.Label(self, text=f"start_webui.py を読み込めませんでした: {self.mod}").pack(anchor="w")
            return

        if API_ONLY_MODE:
            ttk.Label(
                self,
                text="API専用モード: ローカルのWebUI/ComfyUIは起動せず、設定済みAPIへ接続します。",
                wraplength=760,
            ).pack(anchor="w", pady=(0, 8))

        grid = ttk.LabelFrame(self, text="設定", padding=8)
        grid.pack(fill="x")
        ttk.Label(grid, text="使用CPU論理数").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(grid, textvariable=self.cpu, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(grid, textvariable=self.logical_total).grid(row=0, column=2, sticky="w")

        ttk.Label(grid, text="メモリ上限(GB)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(grid, textvariable=self.ram, width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(grid, text="空白で無制限").grid(row=1, column=2, sticky="w")

        ttk.Checkbutton(grid, text="低優先度で実行", variable=self.low_priority).grid(row=2, column=0, columnspan=3, sticky="w", padx=4, pady=4)

        ttk.Label(grid, text="ソフト停止待機秒").grid(row=3, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(grid, textvariable=self.soft_stop, width=10).grid(row=3, column=1, sticky="w")
        ttk.Label(grid, text="ハード停止待機秒").grid(row=4, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(grid, textvariable=self.hard_kill, width=10).grid(row=4, column=1, sticky="w")

        ttk.Label(grid, text="起動フラグ").grid(row=5, column=0, sticky="nw", padx=4, pady=4)
        self.flags_text = tk.Text(grid, height=3, width=70)
        self.flags_text.grid(row=5, column=1, columnspan=3, sticky="we")
        grid.columnconfigure(3, weight=1)

        status_row = ttk.Frame(self)
        status_row.pack(fill="x", pady=6)
        ttk.Label(status_row, text="API ステータス:").pack(side="left")
        self.status_label = ttk.Label(status_row, text="⚫ オフライン", font=("TkDefaultFont", 10, "bold"))
        self.status_label.pack(side="left", padx=6)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="▶️ 起動", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="⏹️ 停止", command=self.stop).pack(side="left", padx=4)
        ttk.Button(buttons, text="� 強制停止", command=self.force_kill).pack(side="left", padx=4)
        ttk.Button(buttons, text="🔄 再起動", command=self.restart).pack(side="left", padx=4)
        ttk.Button(buttons, text="🏥 ヘルスチェック", command=self.health_check).pack(side="left", padx=4)
        ttk.Button(buttons, text="WebUI1111画面を開く", command=lambda: self.open_backend_gui("a1111")).pack(side="left", padx=(16, 4))
        ttk.Button(buttons, text="ComfyUI画面を開く", command=lambda: self.open_backend_gui("comfyui")).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16,4)); self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4); ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    #   "責務": "user configからbackend起動時の初期値を復元する。",
    #   "処理": ["設定fileを読み対応変数へ設定し不正・欠損時は安全に既定値を維持する"],
    #   "引数": [], "戻り値": []
    # }
    def _load_defaults(self):
        if isinstance(self.mod, Exception):
            return
        self.cpu.set(str(getattr(self.mod, "LOGICAL_TO_USE", 4)))
        self.logical_total.set(f"/ {getattr(self.mod, 'LOGICAL_TOTAL', 8)} 論理CPU")
        ram_limit = getattr(self.mod, "RAM_LIMIT_GB", None)
        self.ram.set(str(ram_limit) if ram_limit is not None else "")
        self.low_priority.set(bool(getattr(self.mod, "LOW_PRIORITY", True)))
        self.soft_stop.set(str(getattr(self.mod, "SOFT_STOP_WAIT_SEC", 4.0)))
        self.hard_kill.set(str(getattr(self.mod, "HARD_KILL_WAIT_SEC", 2.0)))
        if self.flags_text is not None:
            self.flags_text.delete("1.0", "end")
            self.flags_text.insert("end", " ".join(getattr(self.mod, "DEFAULT_FLAGS", ["--lowvram", "--disable-safe-unpickle", "--api"])))
        if self.logbox:
            self.logbox.log(f"🎮 {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} タブを起動しました")

        old_log = getattr(self.mod, "_log_msg", None)
        # {
        #   "責務": "起動backendの出力をGUI logへ転送する。",
        #   "処理": ["worker出力をUI threadへenqueueする"],
        #   "引数": {"msg": "backend出力行"}, "戻り値": []
        # }
        def tab_log(msg: str):
            try:
                if old_log:
                    print(msg)
                if self.logbox:
                    self.logbox.log(msg)
            except Exception:
                pass
        self.mod._log_msg = tab_log
        self._refresh_preset_choices()

    # {
    #   "責務": "起動preset名を選択widgetへ反映する。",
    #   "処理": ["PresetStoreのnamesをcombobox候補に設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "起動設定を名前付きpresetとして保存する。",
    #   "処理": ["_valuesから設定を得て保存し選択肢を更新する", "結果をlogへ出す"],
    #   "引数": [], "戻り値": []
    # }
    def save_preset(self):
        try:
            values = {"cpu": self.cpu.get(), "ram": self.ram.get(), "low_priority": self.low_priority.get(), "soft_stop": self.soft_stop.get(), "hard_kill": self.hard_kill.get(), "flags": self.flags_text.get("1.0", "end").strip() if self.flags_text else ""}
            path = self.preset_store.save(self.preset_name.get(), values); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択された起動presetをGUI設定へ復元する。",
    #   "処理": ["PresetStoreから読み対応する変数へ反映する", "結果をlogへ出す"],
    #   "引数": [], "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("cpu", self.cpu), ("ram", self.ram), ("low_priority", self.low_priority), ("soft_stop", self.soft_stop), ("hard_kill", self.hard_kill)):
                if key in values: variable.set(values[key])
            if self.flags_text is not None and "flags" in values: self.flags_text.delete("1.0", "end"); self.flags_text.insert("end", values["flags"])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "現在のbackend起動設定を永続化可能なdictへまとめる。",
    #   "処理": ["選択backend、path、引数、portなどUI状態を読み取る"],
    #   "引数": [], "戻り値": "起動設定dict"
    # }
    def _values(self):
        flags = self.flags_text.get("1.0", "end").strip().split() if self.flags_text else []
        return (
            flags,
            int(self.cpu.get()),
            float(self.ram.get()) if self.ram.get().strip() else None,
            bool(self.low_priority.get()),
            float(self.soft_stop.get()),
            float(self.hard_kill.get()),
        )

    # {
    #   "責務": "選択backendを設定に従って起動する。",
    #   "処理": ["設定を検証して保存する", "backend processを起動し状態監視を開始する"],
    #   "引数": [], "戻り値": []
    # }
    def start(self):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルバックエンドを起動できません")
            return
        if isinstance(self.mod, Exception):
            return
        if getattr(self.mod, "_current_proc", None):
            self.logbox.log(f"⚠️ {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} はすでに起動しています")
            return
        try:
            args = self._values()
        except ValueError as e:
            self.logbox.log(f"❌ 入力エラー: {e}")
            return
        threading.Thread(target=self.mod._start_webui_thread, args=args, daemon=True).start()

    # {
    #   "責務": "現在のbackend processへ通常停止を依頼する。",
    #   "処理": ["process状態を確認して停止signalを送り終了をlogする"],
    #   "引数": [], "戻り値": []
    # }
    def stop(self):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルバックエンドを停止しません")
            return
        if isinstance(self.mod, Exception):
            return
        if not getattr(self.mod, "_current_proc", None):
            self.logbox.log(f"⚠️ {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} は起動していません")
            return
        self.mod._stop_event.set()

    # {
    #   "責務": "応答しないbackend processを強制終了する操作を開始する。",
    #   "処理": ["確認・状態を検査し強制終了workerを開始する"],
    #   "引数": [], "戻り値": []
    # }
    def force_kill(self):
        """既に起動しているプロセスを強制終了する"""
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルプロセスを終了しません")
            return
        if isinstance(self.mod, Exception):
            self.logbox.log("❌ start_webui.py を読み込めません")
            return
        
        # GUI経由で起動したプロセスがあれば、まずそれを停止
        if getattr(self.mod, "_current_proc", None):
            self.mod._stop_event.set()
            self.logbox.log("✅ GUI経由で起動したプロセスを停止しました")
            return
        
        # 外部から起動したプロセスを検出して強制終了
        self.logbox.log("🔍 既に起動しているプロセスを検索中...")
        threading.Thread(target=self._force_kill_thread, daemon=True).start()

    # {
    #   "責務": "backend process treeを強制終了しGUI状態を更新する。",
    #   "処理": ["process treeを終了し結果をUI threadで表示する"],
    #   "引数": [], "戻り値": []
    # }
    def _force_kill_thread(self):
        """強制停止を別スレッドで実行"""
        if isinstance(self.mod, Exception):
            return
        if hasattr(self.mod, "_find_and_kill_webui_process"):
            success = self.mod._find_and_kill_webui_process()
            if not success:
                self.logbox.log("⚠️ プロセスが見つかりませんでした")
        else:
            self.logbox.log("❌ _find_and_kill_webui_process が見つかりません")

    # {
    #   "責務": "選択backendのhealth endpoint確認を開始する。",
    #   "処理": ["health check threadを起動し結果待ちをlogする"],
    #   "引数": [], "戻り値": []
    # }
    def health_check(self):
        """ヘルスチェックボタンのコールバック"""
        if isinstance(self.mod, Exception):
            self.logbox.log("❌ start_webui.py を読み込めません")
            return
        
        self.logbox.log("🏥 ヘルスチェック実行中...")
        threading.Thread(target=self._health_check_thread, daemon=True).start()

    # {
    #   "責務": "backend APIへhealth requestを送り稼働状態を報告する。",
    #   "処理": ["接続先へtimeout付きrequestを送り応答・例外をlogへ通知する"],
    #   "引数": [], "戻り値": []
    # }
    def _health_check_thread(self):
        """ヘルスチェックを別スレッドで実行"""
        if isinstance(self.mod, Exception):
            return
        
        if not hasattr(self.mod, "_health_check_now"):
            self.logbox.log("❌ _health_check_now が見つかりません")
            return
        
        try:
            result = self.mod._health_check_now()
            self.logbox.log(f"ステータス: {result['status']}")
            if result['online']:
                self.logbox.log("✅ API に接続できます")
            else:
                self.logbox.log("❌ API に接続できません")
        except Exception as e:
            self.logbox.log(f"❌ ヘルスチェックエラー: {e}")

    # {
    #   "責務": "backend processを停止後に再起動する。",
    #   "処理": ["停止処理を呼び終了状態を待ってstartを実行する"],
    #   "引数": [], "戻り値": []
    # }
    def restart(self):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルバックエンドを再起動できません")
            return
        if isinstance(self.mod, Exception):
            return
        try:
            args = self._values()
        except ValueError as e:
            self.logbox.log(f"❌ 入力エラー: {e}")
            return
        threading.Thread(target=self.mod._restart_webui, args=args, daemon=True).start()

    # {
    #   "責務": "指定backendのGUI URLを既定browserで開く。",
    #   "処理": ["backendに応じた接続URLを解決してbrowserへ渡す"],
    #   "引数": {"backend": "起動対象backend識別子"}, "戻り値": []
    # }
    def open_backend_gui(self, backend):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではバックエンドGUIを起動できません")
            return
        executable = packaged_executable("KadokaTools")
        if not executable.is_file():
            self.logbox.log(f"配布済みGUIが見つかりません: {executable}")
            return
        environment = os.environ.copy()
        environment["KADOKA_TOOLS_BACKEND"] = backend
        try:
            launch_packaged_executable(executable, "--backend", backend, env=environment)
            self.logbox.log(f"✅ {backend} 用GUIを開きました")
        except OSError as error:
            self.logbox.log(f"GUI起動エラー: {error}")

    # {
    #   "責務": "backend process/API状態を周期的に確認して画面へ反映する。",
    #   "処理": ["processとhealth状態を更新し次回pollを予約する"],
    #   "引数": [], "戻り値": []
    # }
    def _poll_status(self):
        if not isinstance(self.mod, Exception) and hasattr(self, "status_label"):
            self.status_label.config(text=getattr(self.mod, "_api_status", "⚫ オフライン"))
        self.after(500, self._poll_status)
