from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore
from ..subapp_runtime import launch_packaged_executable, packaged_executable


# {
#   責務: [StartWebUITab: local backend lifecycle, resource limits, status checks, packaged GUI launching, and presetsを管理するtab]
#   処理: [bridge GUI controls to embedded backend lifecycle and API-only policy]
#   フィールド: [mod, preset_store/name, CPU/RAM/priority/stop timers, flags_text, logbox, status_label]
# }
class StartWebUITab(ttk.Frame):
    # {
    #   責務: [__init__: backend module, resource-limit fields, and UI stateを初期化する]
    #   処理: [load embedded module handle, initialize Tk variables, build controls, restore defaults, and schedule status polling]
    #   引数: [master]
    #   戻り値: [処理結果]
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
    #   責務: [_build: backend resource controls, flags, status, lifecycle actions, and preset UIを構築する]
    #   処理: [respect API-only mode and unavailable module states while composing widgets]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        if isinstance(self.mod, Exception):
            ttk.Label(self, text=f"start_webui.py を読み込めませんでした: {self.mod}").pack(
                anchor="w"
            )
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

        ttk.Checkbutton(grid, text="低優先度で実行", variable=self.low_priority).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=4, pady=4
        )

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
        self.status_label = ttk.Label(
            status_row, text="⚫ オフライン", font=("TkDefaultFont", 10, "bold")
        )
        self.status_label.pack(side="left", padx=6)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="▶️ 起動", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="⏹️ 停止", command=self.stop).pack(side="left", padx=4)
        ttk.Button(buttons, text="� 強制停止", command=self.force_kill).pack(side="left", padx=4)
        ttk.Button(buttons, text="🔄 再起動", command=self.restart).pack(side="left", padx=4)
        ttk.Button(buttons, text="🏥 ヘルスチェック", command=self.health_check).pack(
            side="left", padx=4
        )
        ttk.Button(
            buttons, text="WebUI1111画面を開く", command=lambda: self.open_backend_gui("a1111")
        ).pack(side="left", padx=(16, 4))
        ttk.Button(
            buttons, text="ComfyUI画面を開く", command=lambda: self.open_backend_gui("comfyui")
        ).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    #   責務: [_load_defaults: embedded backend defaults and log callbackをGUI controlsへ接続する]
    #   処理: [restore resource limits and launch flags, wrap backend logging, and refresh presets]
    #   引数: [なし]
    #   戻り値: [処理結果]
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
            self.flags_text.insert(
                "end",
                " ".join(
                    getattr(
                        self.mod, "DEFAULT_FLAGS", ["--lowvram", "--disable-safe-unpickle", "--api"]
                    )
                ),
            )
        if self.logbox:
            self.logbox.log(f"🎮 {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} タブを起動しました")

        old_log = getattr(self.mod, "_log_msg", None)

        # {
        #   責務: [tab_log: backend log callbackをterminal-compatible output and GUI logへforwardする]
        #   処理: [preserve prior console behavior when present and append to logbox]
        #   引数: [msg]
        #   戻り値: [処理結果]
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
    #   責務: [_refresh_preset_choices: preset dropdownをavailable namesで更新する]
    #   処理: [configure values from PresetStore]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   責務: [save_preset: CPU/RAM/priority/shutdown/launch flagsをpresetへ保存する]
    #   処理: [serialize GUI state, refresh selector, and log errors]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def save_preset(self):
        try:
            values = {
                "cpu": self.cpu.get(),
                "ram": self.ram.get(),
                "low_priority": self.low_priority.get(),
                "soft_stop": self.soft_stop.get(),
                "hard_kill": self.hard_kill.get(),
                "flags": self.flags_text.get("1.0", "end").strip() if self.flags_text else "",
            }
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   責務: [load_preset: selected presetからbackend resource and launch settingsを復元する]
    #   処理: [restore known controls and optional flags text]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (
                ("cpu", self.cpu),
                ("ram", self.ram),
                ("low_priority", self.low_priority),
                ("soft_stop", self.soft_stop),
                ("hard_kill", self.hard_kill),
            ):
                if key in values:
                    variable.set(values[key])
            if self.flags_text is not None and "flags" in values:
                self.flags_text.delete("1.0", "end")
                self.flags_text.insert("end", values["flags"])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   責務: [_values: GUI text fieldsをtyped backend launch argument tupleへparseする]
    #   処理: [split flags and parse integer/float values with blank RAM as None]
    #   引数: [なし]
    #   戻り値: [処理結果]
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
    #   責務: [start: 検証済みの起動設定でbackend開始要求を予約してworkerを起動する]
    #   処理: [1: API-only・backend状態・入力を確認する, 2: generationを予約する, 3: token付きworkerを起動する]
    #   引数: [self: backend制御UI]
    #   戻り値: []
    # }
    def start(self):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルバックエンドを起動できません")
            return
        if isinstance(self.mod, Exception):
            return
        if any(
            getattr(self.mod, attribute, False)
            for attribute in ("_current_proc", "_lifecycle_active", "_desired_running")
        ):
            self.logbox.log(
                f"⚠️ {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} はすでに起動しています"
            )
            return
        try:
            args = self._values()
        except ValueError as e:
            self.logbox.log(f"❌ 入力エラー: {e}")
            return
        generation = self.mod.request_start()
        if generation is None:
            self.logbox.log(
                f"⚠️ {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} はすでに起動しています"
            )
            return
        threading.Thread(
            target=self.mod._start_webui_thread,
            args=args,
            kwargs={"_generation": generation},
            daemon=True,
        ).start()

    # {
    # 責務: [stop: 起動中または開始中のbackend lifecycleを停止する]
    # 処理: [1: API-only制約を確認する, 2: request_stopでpending restartも取り消す]
    # 引数: [self]
    # 戻り値: []
    # }
    def stop(self):
        if API_ONLY_MODE:
            self.logbox.log("API専用モードではローカルバックエンドを停止しません")
            return
        if isinstance(self.mod, Exception):
            return
        if not any(
            getattr(self.mod, attribute, False)
            for attribute in ("_current_proc", "_lifecycle_active", "_desired_running")
        ):
            self.logbox.log(f"⚠️ {getattr(self.mod, 'DISPLAY_NAME', 'WebUI')} は起動していません")
            return
        self.mod.request_stop()

    # {
    # 責務: [force_kill: backendを停止するか外部portのprocessを終了する]
    # 処理: [1: 管理中lifecycleを停止する, 2: 未管理の場合は外部processを検索する]
    # 引数: [self]
    # 戻り値: []
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
        if any(
            getattr(self.mod, attribute, False)
            for attribute in ("_current_proc", "_lifecycle_active", "_desired_running")
        ):
            self.mod.request_stop()
            self.logbox.log("✅ GUI経由で起動したプロセスを停止しました")
            return

        # 外部から起動したプロセスを検出して強制終了
        self.logbox.log("🔍 既に起動しているプロセスを検索中...")
        threading.Thread(target=self._force_kill_thread, daemon=True).start()

    # {
    #   責務: [_force_kill_thread: unmanaged backend processをbackgroundで検索し終了する]
    #   処理: [call embedded finder when available and log missing process/module capability]
    #   引数: [なし]
    #   戻り値: [処理結果]
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
    #   責務: [health_check: backend API health-check workerを開始する]
    #   処理: [validate module and launch asynchronous callback]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def health_check(self):
        """ヘルスチェックボタンのコールバック"""
        if isinstance(self.mod, Exception):
            self.logbox.log("❌ start_webui.py を読み込めません")
            return

        self.logbox.log("🏥 ヘルスチェック実行中...")
        threading.Thread(target=self._health_check_thread, daemon=True).start()

    # {
    #   責務: [_health_check_thread: backend health responseを問い合わせてonline stateをlogする]
    #   処理: [validate method availability, call checker, and report status/errors]
    #   引数: [なし]
    #   戻り値: [処理結果]
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
            if result["online"]:
                self.logbox.log("✅ API に接続できます")
            else:
                self.logbox.log("❌ API に接続できません")
        except Exception as e:
            self.logbox.log(f"❌ ヘルスチェックエラー: {e}")

    # {
    #   責務: [restart: validated local backend settingsでrestart workerを開始する]
    #   処理: [respect API-only/module state, parse settings, and spawn restart callback]
    #   引数: [なし]
    #   戻り値: [処理結果]
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
    #   責務: [open_backend_gui: selected backend用packaged KadokaTools GUIを起動する]
    #   処理: [respect API-only mode, resolve sibling executable, set backend environment, and report OS launch errors]
    #   引数: [backend]
    #   戻り値: [処理結果]
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
    #   責務: [_poll_status: embedded module API statusをlabelへ反映し次回pollをscheduleする]
    #   処理: [read current status when available and schedule after callback]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _poll_status(self):
        if not isinstance(self.mod, Exception) and hasattr(self, "status_label"):
            self.status_label.config(text=getattr(self.mod, "_api_status", "⚫ オフライン"))
        self.after(500, self._poll_status)
