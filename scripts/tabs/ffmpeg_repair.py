from ..context import *
from ..context import _safe_thread
from ..services import *
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..widgets.preset_store import PresetStore

# {
#   "責務": "FFmpegで動画コンテナ・timestamp・映像音声を修復するUI。",
#   "フィールド": ["input_file: 入力動画", "output_file: 出力先", "mode: 修復方式", "cpu_cores: subprocessに適用するCPU上限", "preset_store: 設定保存先", "preset_name: 選択プリセット", "logbox: 実行ログ"]
# }
class FfmpegRepairTab(ttk.Frame):
    # {
    #   "責務": "入力・出力・修復方式・CPU数を初期化して画面を構築する。",
    #   "処理": ["設定値とプリセット保存先を初期化する", "入力欄・修復方式・操作ボタン・ログを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master,padding=10)
        self.input_file=tk.StringVar(value=USER_PATHS["ffmpeg_input_file"]); self.output_file=tk.StringVar(value=USER_PATHS["ffmpeg_output_file"]); self.mode=tk.StringVar(value="auto"); self.cpu_cores=tk.StringVar()
        self.preset_store = PresetStore("ffmpeg_repair"); self.preset_name = tk.StringVar()
        LabeledPathRow(self,"input_file",self.input_file,mode="file").pack(fill="x",pady=4); LabeledPathRow(self,"output_file",self.output_file,mode="save").pack(fill="x",pady=4)
        r=ttk.Frame(self); r.pack(fill="x",pady=4); ttk.Label(r,text="mode",width=22).pack(side="left"); ttk.Combobox(r,textvariable=self.mode,values=["auto","remux","genpts","reencode"],state="readonly",width=12).pack(side="left")
        cpu_row=ttk.Frame(self); cpu_row.pack(fill="x",pady=4); ttk.Label(cpu_row,text="使用CPU論理数",width=22).pack(side="left"); ttk.Entry(cpu_row,textvariable=self.cpu_cores,width=12).pack(side="left"); ttk.Label(cpu_row,text="空欄なら制限なし").pack(side="left",padx=6)
        buttons = ttk.Frame(self); buttons.pack(fill="x",pady=8)
        ttk.Button(buttons,text="修復実行",command=lambda:_safe_thread(self.logbox,self.run)).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh_preset_choices()
    # {
    #   "責務": "プリセット名一覧を選択UIへ反映する。",
    #   "処理": ["保存済みプリセット名を取得しcomboboxへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "現在の入出力先・修復方式・CPU上限を保存する。",
    #   "処理": ["設定値をプリセットへ保存する", "表示名と選択肢を更新し結果をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_file": self.input_file.get(), "output_file": self.output_file.get(), "mode": self.mode.get(), "cpu_cores": self.cpu_cores.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    # {
    #   "責務": "選択した修復プリセットを画面設定へ読み込む。",
    #   "処理": ["保存値がある項目を各入力状態へ反映する", "成否をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.input_file.set(values.get("input_file", self.input_file.get())); self.output_file.set(values.get("output_file", self.output_file.get())); self.mode.set(values.get("mode", self.mode.get())); self.cpu_cores.set(values.get("cpu_cores", self.cpu_cores.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
    # {
    #   "責務": "CPU上限を適用してFFmpeg commandを実行し結果を記録する。",
    #   "処理": ["commandを起動しProcessCpuLimiterを適用する", "終了まで出力を収集してログへ出す"],
    #   "引数": {"cmd": "実行するargument list", "cpu_cores": "CPU論理数の上限設定"},
    #   "戻り値": "終了コードが0の場合True、それ以外はFalse"
    # }
    def _cmd(self,cmd,cpu_cores):
        self.logbox.log("実行: "+" ".join(cmd)); process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="ignore"); ProcessCpuLimiter.apply(process.pid,cpu_cores); output,_=process.communicate(); self.logbox.log(output); return process.returncode==0
    # {
    #   "責務": "設定と入力を検証し、選択方式またはfallback順で動画を修復する。",
    #   "処理": ["ffmpeg・入力・CPU設定を検証する", "remux、timestamp修正、再encodeを選択順に試す", "成否と出力先をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        if shutil.which("ffmpeg") is None: self.logbox.log("ffmpeg が PATH にありません"); return
        inp=self.input_file.get().strip(); out=self.output_file.get().strip(); mode=self.mode.get()
        cpu_cores=self.cpu_cores.get().strip()
        try: cpu_count=ProcessCpuLimiter.core_count(cpu_cores)
        except ValueError: self.logbox.log(f"使用CPU論理数には数値を指定してください: {cpu_cores}"); return
        if not os.path.isfile(inp): self.logbox.log(f"入力ファイルが存在しません: {inp}"); return
        if os.path.dirname(out): os.makedirs(os.path.dirname(out),exist_ok=True)
        self.logbox.log("CPU制限: なし" if cpu_count is None else f"CPU制限: 論理CPU 0-{cpu_count - 1}")
        remux=lambda o:self._cmd(["ffmpeg","-y","-err_detect","ignore_err","-i",inp,"-map","0","-c","copy","-fflags","+genpts",o],cpu_cores)
        genpts=lambda o:self._cmd(["ffmpeg","-y","-err_detect","ignore_err","-i",inp,"-map","0","-c","copy","-fflags","+genpts+discardcorrupt",o],cpu_cores)
        reenc=lambda o:self._cmd(["ffmpeg","-y","-err_detect","ignore_err","-i",inp,"-c:v","libx264","-preset","fast","-crf","23","-c:a","aac","-b:a","128k",o],cpu_cores)
        ok=False
        if mode=="remux": ok=remux(out)
        elif mode=="genpts": ok=genpts(out)
        elif mode=="reencode": ok=reenc(out)
        else:
            import tempfile
            fd,tmp=tempfile.mkstemp(suffix=os.path.splitext(out)[1] or ".mp4"); os.close(fd)
            if remux(tmp): os.replace(tmp,out); ok=True
            else:
                try: os.remove(tmp)
                except Exception: pass
                fd,tmp=tempfile.mkstemp(suffix=os.path.splitext(out)[1] or ".mp4"); os.close(fd)
                if genpts(tmp): os.replace(tmp,out); ok=True
                else:
                    try: os.remove(tmp)
                    except Exception: pass
                    ok=reenc(out)
        self.logbox.log(("修復成功: " if ok else "修復失敗: ")+out)
