from ..context import *
from ..context import _safe_thread
from ..services import *
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..widgets.preset_store import PresetStore

# {
#   "責務": "動画folder内の動画からrandom frameを並列抽出するUI。",
#   "フィールド": ["DEFAULT_INPUT_DIR/DEFAULT_OUTPUT_DIR: 既定path", "VIDEO_EXTS: 対象拡張子", "input_dir/output_dir: 入出力folder", "frames/image_format: 抽出数と形式", "max_workers/cpu_cores/low_priority: 実行制限", "preset_store/preset_name/preset_combo: 設定管理", "logbox: 実行ログ"]
# }
class ScreenshotFromMovieTab(ttk.Frame):
    DEFAULT_INPUT_DIR = USER_PATHS["screenshot_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["screenshot_output_dir"]
    VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v")
    # {
    #   "責務": "抽出数・形式・並列数・CPU優先度を初期化し画面を作る。",
    #   "処理": ["入出力と処理optionを初期化する", "path・parameter・preset・log UIを配置しpreset候補を読む"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.output_dir = tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        self.frames = tk.StringVar(value="100")
        self.image_format = tk.StringVar(value="jpg")
        self.max_workers = tk.StringVar(value=str(max(1, (os.cpu_count() or 4)//2)))
        self.cpu_cores = tk.StringVar(value=str(max(1, (os.cpu_count() or 4)//2)))
        self.low_priority = tk.BooleanVar(value=True)
        self.preset_store = PresetStore("screenshot_from_movie")
        self.preset_name = tk.StringVar()
        LabeledPathRow(self, "INPUT_DIR", self.input_dir, mode="dir").pack(fill="x", pady=4)
        LabeledPathRow(self, "OUTPUT_DIR", self.output_dir, mode="dir").pack(fill="x", pady=4)
        row=ttk.Frame(self); row.pack(fill="x", pady=4)
        for label,var in [("FRAMES_PER_VIDEO",self.frames),("IMAGE_FORMAT",self.image_format),("MAX_WORKERS",self.max_workers)]:
            ttk.Label(row,text=label).pack(side="left"); ttk.Entry(row,textvariable=var,width=8).pack(side="left",padx=(4,12))
        row2=ttk.Frame(self); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="使用CPU論理数").pack(side="left")
        ttk.Entry(row2, textvariable=self.cpu_cores, width=8).pack(side="left", padx=(4,12))
        ttk.Label(row2, text="空欄なら制限なし").pack(side="left")
        ttk.Checkbutton(self, text="ffmpeg低優先度", variable=self.low_priority).pack(anchor="w")
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Start", command=lambda:_safe_thread(self.logbox,self.run)).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both", expand=True); self._refresh_preset_choices()
    # {
    #   "責務": "保存済み抽出preset名を選択UIへ反映する。",
    #   "処理": ["PresetStoreからnamesを得てcomboboxを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "動画抽出path・format・並列・CPU優先度設定をpresetへ保存する。",
    #   "処理": ["現在値を保存する", "preset名・候補と完了logを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            values = {"input_dir": self.input_dir.get(), "output_dir": self.output_dir.get(), "frames": self.frames.get(), "image_format": self.image_format.get(), "max_workers": self.max_workers.get(), "cpu_cores": self.cpu_cores.get(), "low_priority": self.low_priority.get()}
            path = self.preset_store.save(self.preset_name.get(), values); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    # {
    #   "責務": "選択presetから動画抽出条件を復元する。",
    #   "処理": ["保存値をpath・format・limit variableへ設定する", "結果をlogへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.frames.set(str(values.get("frames", self.frames.get()))); self.image_format.set(values.get("image_format", self.image_format.get())); self.max_workers.set(str(values.get("max_workers", self.max_workers.get()))); self.cpu_cores.set(str(values.get("cpu_cores", self.cpu_cores.get()))); self.low_priority.set(bool(values.get("low_priority", self.low_priority.get()))); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
    # {
    #   "責務": "ffprobeで動画の再生時間を取得する。",
    #   "処理": ["ffprobeをjson出力で実行する", "format.durationをfloatに変換する"],
    #   "引数": {"path": "動画file path"},
    #   "戻り値": "動画durationの秒数"
    # }
    def _duration(self, path):
        import json
        p=subprocess.run(["ffprobe","-v","error","-print_format","json","-show_format",path],capture_output=True,text=True,encoding="utf-8",errors="ignore",check=True)
        return float(json.loads(p.stdout)["format"]["duration"])
    # {
    #   "責務": "ffmpegを低priorityで起動するためのplatform引数を作る。",
    #   "処理": ["低priority無効時は空mappingを返す", "Windows creation flagまたはUnix niceness callbackを返す"],
    #   "引数": [],
    #   "戻り値": "subprocess.Popenへ渡すkeyword mapping"
    # }
    def _low_kwargs(self):
        if not self.low_priority.get(): return {}
        if os.name=="nt": return {"creationflags":0x00000040}
        return {"preexec_fn":lambda: os.nice(19)}

    # {
    #   "責務": "動画の指定timestampから1frameを画像fileへ抽出する。",
    #   "処理": ["出力folderを作る", "ffmpegを指定位置で実行しCPU制限を適用して完了待ちする"],
    #   "引数": {"video": "入力動画path", "ts": "抽出位置の秒数", "out": "出力画像path", "cpu_cores": "CPU logical core limit"},
    #   "戻り値": []
    # }
    def _extract(self, video, ts, out, cpu_cores):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cmd=["ffmpeg","-y","-ss",f"{ts:.6f}","-i",video,"-frames:v","1","-q:v","2",out]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **self._low_kwargs())
        ProcessCpuLimiter.apply(proc.pid, cpu_cores)
        proc.wait()
    # {
    #   "責務": "入力動画ごとに指定数のrandom frameを並列抽出する。",
    #   "処理": ["format・folder・worker・CPU条件を検証する", "各動画durationから抽出時刻を選ぶ", "ThreadPoolExecutorでffmpeg抽出し処理状況をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        import random
        from concurrent.futures import ThreadPoolExecutor, as_completed
        inp=self.input_dir.get().strip(); outroot=self.output_dir.get().strip()
        frames=int(self.frames.get()); fmt=self.image_format.get().strip().lower()
        workers=max(1,int(self.max_workers.get()))
        cpu_cores = self.cpu_cores.get().strip()
        try:
            cpu_count = ProcessCpuLimiter.core_count(cpu_cores)
        except ValueError:
            self.logbox.log(f"使用CPU論理数には数値を指定してください: {cpu_cores}"); return
        if fmt=="jpeg": fmt="jpg"
        if fmt not in ("jpg","png"): self.logbox.log("IMAGE_FORMAT は jpg/png/jpeg"); return
        if not os.path.isdir(inp): self.logbox.log(f"入力フォルダがありません: {inp}"); return
        self.logbox.log("CPU制限: なし" if cpu_count is None else f"CPU制限: 論理CPU 0-{cpu_count - 1}")
        os.makedirs(outroot, exist_ok=True)
        videos=[f for f in os.listdir(inp) if f.lower().endswith(self.VIDEO_EXTS)]
        self.logbox.log(f"動画数: {len(videos)}")
        for f in videos:
            try:
                video=os.path.join(inp,f); dur=self._duration(video)
                name=Path(video).stem[:180]; outdir=os.path.join(outroot,name); os.makedirs(outdir, exist_ok=True)
                times=sorted(random.sample([random.uniform(0,dur) for _ in range(frames*2)], frames))
                self.logbox.log(f"Processing: {video}")
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs=[ex.submit(self._extract, video, ts, os.path.join(outdir, f"frame_{i:03d}.{fmt}"), cpu_cores) for i,ts in enumerate(times)]
                    for fu in as_completed(futs): fu.result()
                self.logbox.log(f"完了: {f}")
            except Exception as e:
                self.logbox.log(f"❌ {f}: {e}")
        self.logbox.log("全処理完了")
