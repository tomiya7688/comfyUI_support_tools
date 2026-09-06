from __future__ import annotations
import shutil, threading
from pathlib import Path
from ..context import *
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..backend.video_reencoder import VideoReencoder
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore

class VideoReencoderTab(ttk.Frame):
    VIDEO_EXTENSIONS={".mp4",".mkv",".avi",".mov",".webm",".m4v"}
    def __init__(self,master):
        super().__init__(master,padding=10); self.input_dir=tk.StringVar(); self.output_dir=tk.StringVar(value=str(USER_DATA_DIR/"output"/"reencoder")); self.recursive=tk.BooleanVar(value=True); self.scene_split=tk.BooleanVar(value=False); self.scene_threshold=tk.StringVar(value="0.40"); self.auto_settings=tk.BooleanVar(value=False); self.codec=tk.StringVar(value="h264"); self.preset=tk.StringVar(value="medium"); self.max_height=tk.StringVar(value="1080"); self.target_mb=tk.StringVar(); self.crf=tk.StringVar(value="23"); self.audio_kbps=tk.StringVar(value="128"); self.cpu_cores=tk.StringVar(); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("video_reencoder"); self._build()
    def _build(self):
        LabeledPathRow(self,"入力動画フォルダ",self.input_dir,mode="dir").pack(fill="x",pady=3); LabeledPathRow(self,"出力先",self.output_dir,mode="dir").pack(fill="x",pady=3); ttk.Checkbutton(self,text="サブフォルダも処理",variable=self.recursive).pack(anchor="w"); scene_row=ttk.Frame(self); scene_row.pack(fill="x",pady=2); ttk.Checkbutton(scene_row,text="シーン検出で分割出力",variable=self.scene_split).pack(side="left"); ttk.Label(scene_row,text="閾値").pack(side="left",padx=(12,4)); ttk.Entry(scene_row,textvariable=self.scene_threshold,width=8).pack(side="left"); ttk.Label(scene_row,text="（0.01〜0.99）").pack(side="left",padx=4); ttk.Checkbutton(self,text="動画内容から設定を自動提案（解像度基準）",variable=self.auto_settings).pack(anchor="w",pady=2)
        frame=ttk.LabelFrame(self,text="再エンコード設定",padding=6); frame.pack(fill="x",pady=5)
        for label,var,choices in (("動画コーデック",self.codec,["h264","h265"]),("速度プリセット",self.preset,["fast","medium","slow"]),("最大高さ（0=維持）",self.max_height,None),("目標サイズMB（空欄=CRF）",self.target_mb,None),("CRF",self.crf,None),("音声kbps",self.audio_kbps,None),("使用CPU論理数",self.cpu_cores,None)):
            row=ttk.Frame(frame); row.pack(fill="x",pady=2); ttk.Label(row,text=label,width=28).pack(side="left"); (ttk.Combobox(row,textvariable=var,values=choices,state="readonly",width=14) if choices else ttk.Entry(row,textvariable=var,width=14)).pack(side="left")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="再エンコード開始",command=self.start).pack(side="left",padx=4); self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None: self.logbox.log("ffmpeg と ffprobe が PATH に必要です"); return
        root,out=Path(self.input_dir.get().strip()),Path(self.output_dir.get().strip())
        if not root.is_dir(): self.logbox.log(f"入力動画フォルダがありません: {root}"); return
        try: settings={"codec":self.codec.get(),"preset":self.preset.get(),"max_height":int(self.max_height.get()),"target_mb":float(self.target_mb.get() or 0),"crf":int(self.crf.get()),"audio_kbps":int(self.audio_kbps.get())}; cpu=ProcessCpuLimiter.core_count(self.cpu_cores.get().strip())
        except ValueError as error: self.logbox.log(f"設定値エラー: {error}"); return
        videos=sorted((p for p in (root.rglob("*") if self.recursive.get() else root.iterdir()) if p.is_file() and p.suffix.lower() in self.VIDEO_EXTENSIONS),key=lambda p:p.as_posix().casefold()); encoder=VideoReencoder(); self.logbox.log(f"開始: {len(videos)}動画")
        try: scene_threshold=float(self.scene_threshold.get())
        except ValueError: self.logbox.log("シーン閾値は数値で指定してください"); return
        if not 0.01 <= scene_threshold <= 0.99: self.logbox.log("シーン閾値は0.01〜0.99で指定してください"); return
        for source in videos:
            target=(out/source.relative_to(root)).with_suffix(".mp4")
            try:
                target.parent.mkdir(parents=True,exist_ok=True); duration=encoder.duration_seconds(source)
                if self.auto_settings.get():
                    recommendation=encoder.recommend_settings(encoder.probe_video(source)); settings.update(recommendation); self.logbox.log(f"自動設定: {source.name} {recommendation}")
                if not self.scene_split.get(): commands=[(target,encoder.build_command(source,target,settings,duration))]
                else:
                    points=[0.0,*encoder.scene_timestamps(source,scene_threshold),duration]; commands=[(target.with_name(f"{target.stem}_scene{index:03d}{target.suffix}"),encoder.build_segment_command(source,target.with_name(f"{target.stem}_scene{index:03d}{target.suffix}"),settings,start,end)) for index,(start,end) in enumerate(zip(points,points[1:]),1) if end-start >= 0.1]; self.logbox.log(f"シーン分割: {len(commands)}区間")
                for segment_target,command in commands:
                    self.logbox.log("実行: "+" ".join(command)); self.logbox.log(("✅ " if encoder.run(command,cpu,self.logbox.log) else "❌ 失敗: ")+str(segment_target))
            except Exception as error: self.logbox.log(f"❌ {source}: {error}")
