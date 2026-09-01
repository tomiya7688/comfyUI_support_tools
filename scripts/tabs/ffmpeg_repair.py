from ..context import *
from ..context import _safe_thread
from ..services import *
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..widgets.preset_store import PresetStore

class FfmpegRepairTab(ttk.Frame):
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
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_file": self.input_file.get(), "output_file": self.output_file.get(), "mode": self.mode.get(), "cpu_cores": self.cpu_cores.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.input_file.set(values.get("input_file", self.input_file.get())); self.output_file.set(values.get("output_file", self.output_file.get())); self.mode.set(values.get("mode", self.mode.get())); self.cpu_cores.set(values.get("cpu_cores", self.cpu_cores.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
    def _cmd(self,cmd,cpu_cores):
        self.logbox.log("実行: "+" ".join(cmd)); process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="ignore"); ProcessCpuLimiter.apply(process.pid,cpu_cores); output,_=process.communicate(); self.logbox.log(output); return process.returncode==0
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
