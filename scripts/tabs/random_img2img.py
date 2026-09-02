from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class RandomImg2ImgTab(ttk.Frame):
    TAGGER_PRESETS = {
        "A1111 standard": "http://127.0.0.1:7860/sdapi/v1/interrogate",
        "PixAI v0.9": PIXAI_TAGGER_API_URL,
    }
    DEFAULT_INPUT_DIR = USER_PATHS["random_img2img_input_dir"]
    DEFAULT_OUTPUT_DIR = str(
        (RUNTIME_DIR / "output" / "KadokaTools_img2img")
        if RUNTIME_BACKEND == "comfyui"
        else (A1111_DIR / "outputs" / "img2img-images" / "amahane_yukiko_img2img")
    )
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.stop_event=threading.Event()
        self.preset_store=PresetStore("random_img2img"); self.preset_name=tk.StringVar()
        self.input_dir=tk.StringVar(value=self.DEFAULT_INPUT_DIR); self.output_dir=tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        default_tagger="PixAI v0.9" if RUNTIME_BACKEND == "comfyui" else "A1111 standard"
        self.tagger_kind=tk.StringVar(value=default_tagger)
        self.use_tagger=tk.BooleanVar(value=True)
        self.api_interrogate=tk.StringVar(value=self.TAGGER_PRESETS[default_tagger])
        self.api_img2img=tk.StringVar(value="http://127.0.0.1:8188" if RUNTIME_BACKEND == "comfyui" else "http://127.0.0.1:7860/sdapi/v1/img2img")
        self.threshold=tk.StringVar(value="0.35"); self.character_threshold=tk.StringVar(value="0.85"); self.additional=tk.StringVar(value="best quality"); self.manual_prompt=tk.StringVar()
        self.exclude=tk.StringVar(value="worst quality, low quality, normal quality, lowres, blurry, jpeg artifacts, bad anatomy, bad hands, extra fingers, missing fingers, poorly drawn hands, bad feet, missing arms, missing legs, extra limbs, fused fingers, deformed hands, text, error, signature, watermark, username, artist name, long neck, extra eyes, disfigured, mutation, mutated, ugly, extra arms, bad proportions, missing body parts, malformed limbs, poorly drawn face, poorly drawn eyes, cross-eye, wrong fingers, animal ears, virtual youtuber, animal face, beast face, monster girl, wrong proportions, deformed, furry, halo, kemomimi, realistic, futanari, censored, sfw")
        self.negative=tk.StringVar(value="(worst quality, low quality:1.4), (normal quality:1.1), lowres, blurry, jpeg artifacts, bad anatomy, bad hands, extra fingers, missing fingers, poorly drawn hands, bad feet, missing arms, missing legs, extra limbs, fused fingers, deformed hands, text, error, signature, watermark, username, artist name, long neck, extra limbs, extra eyes, disfigured, mutation, mutated, ugly, extra arms, bad proportions, missing body parts, malformed limbs, poorly drawn face, poorly drawn eyes, cross-eye, wrong fingers,animal ears,animal face,beast face,monster girl,wrong proportions,deformed,furry,text,halo, kemomimi,realistic,futanari")
        self.steps=tk.StringVar(value="25"); self.cfg=tk.StringVar(value="6.5"); self.width=tk.StringVar(value="960"); self.height=tk.StringVar(value="1280"); self.denoise=tk.StringVar(value="0.75"); self.sampler=tk.StringVar(value="Euler a"); self.checkpoint=tk.StringVar(value="shiitakeMix_v20.safetensors" if RUNTIME_BACKEND == "comfyui" else "rinIllusionRNSFW_v20"); self.loops=tk.StringVar(value="100000")
        LabeledPathRow(self,"INPUT_DIR",self.input_dir,mode="dir").pack(fill="x",pady=2); LabeledPathRow(self,"OUTPUT_DIR",self.output_dir,mode="dir").pack(fill="x",pady=2)
        tagger_row=ttk.Frame(self); tagger_row.pack(fill="x",pady=2); ttk.Checkbutton(tagger_row,text="Taggerで入力画像からタグを取得",variable=self.use_tagger).pack(side="left"); ttk.Label(tagger_row,text="TAGGER",width=12).pack(side="left"); tagger_combo=ttk.Combobox(tagger_row,textvariable=self.tagger_kind,values=list(self.TAGGER_PRESETS),state="readonly",width=24); tagger_combo.pack(side="left"); tagger_combo.bind("<<ComboboxSelected>>",self._apply_tagger_preset); ttk.Button(tagger_row,text="PixAI API起動",command=self.start_pixai_api).pack(side="left",padx=(12,4)); ttk.Button(tagger_row,text="PixAI API停止",command=self.stop_pixai_api).pack(side="left",padx=4)
        for label,var in [("API_INTERROGATE",self.api_interrogate),("API_IMG2IMG",self.api_img2img),("手動プロンプト（Taggerなし時）",self.manual_prompt),("ADDITIONAL_TAGS",self.additional)]:
            r=ttk.Frame(self); r.pack(fill="x",pady=2); ttk.Label(r,text=label,width=22).pack(side="left"); ttk.Entry(r,textvariable=var).pack(side="left",fill="x",expand=True)
        grid=ttk.Frame(self); grid.pack(fill="x",pady=4)
        for i,(label,var) in enumerate([("THRESHOLD",self.threshold),("CHAR_THRESHOLD",self.character_threshold),("STEPS",self.steps),("CFG",self.cfg),("WIDTH",self.width),("HEIGHT",self.height),("DENOISE",self.denoise),("SAMPLER",self.sampler),("CHECKPOINT",self.checkpoint),("LOOPS",self.loops)]):
            r,c=divmod(i,3); ttk.Label(grid,text=label).grid(row=r,column=c*2,sticky="w")
            widget = ttk.Combobox(grid,textvariable=var,width=20) if label in {"SAMPLER","CHECKPOINT"} else ttk.Entry(grid,textvariable=var,width=20)
            widget.grid(row=r,column=c*2+1,sticky="we",padx=3)
            if label == "SAMPLER": self.sampler_combo = widget
            if label == "CHECKPOINT": self.checkpoint_combo = widget
        btn=ttk.Frame(self); btn.pack(fill="x"); ttk.Button(btn,text="開始",command=self.start).pack(side="left",padx=4); ttk.Button(btn,text="停止",command=self.stop).pack(side="left",padx=4); ttk.Button(btn,text="モデル候補更新",command=self.refresh_backend_choices).pack(side="left",padx=12); ttk.Label(btn,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(btn,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(btn,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(btn,text="読込",command=self.load_preset).pack(side="left",padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
        self.logbox.log("※ 生成中にAPIエラーが出てもGUIは継続します。")
        if RUNTIME_BACKEND == "comfyui":
            self.logbox.log("※ タグ取得にはPixAI API（7861）、生成にはComfyUI API（8188）を使います。")
        self._load_local_backend_choices()
        self._refresh_preset_choices()

    def _preset_values(self):
        values = {key: variable.get() for key, variable in (("input_dir",self.input_dir),("output_dir",self.output_dir),("tagger_kind",self.tagger_kind),("api_interrogate",self.api_interrogate),("api_img2img",self.api_img2img),("threshold",self.threshold),("character_threshold",self.character_threshold),("additional",self.additional),("manual_prompt",self.manual_prompt),("exclude",self.exclude),("negative",self.negative),("steps",self.steps),("cfg",self.cfg),("width",self.width),("height",self.height),("denoise",self.denoise),("sampler",self.sampler),("checkpoint",self.checkpoint),("loops",self.loops))}
        values["use_tagger"] = self.use_tagger.get()
        return values

    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path=self.preset_store.save(self.preset_name.get(),self._preset_values()); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values=self.preset_store.load(self.preset_name.get())
            for key,variable in (("input_dir",self.input_dir),("output_dir",self.output_dir),("tagger_kind",self.tagger_kind),("api_interrogate",self.api_interrogate),("api_img2img",self.api_img2img),("threshold",self.threshold),("character_threshold",self.character_threshold),("additional",self.additional),("manual_prompt",self.manual_prompt),("exclude",self.exclude),("negative",self.negative),("steps",self.steps),("cfg",self.cfg),("width",self.width),("height",self.height),("denoise",self.denoise),("sampler",self.sampler),("checkpoint",self.checkpoint),("loops",self.loops)):
                if key in values: variable.set(values[key])
            self.use_tagger.set(values.get("use_tagger", True))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def _apply_tagger_preset(self, _event=None):
        self.api_interrogate.set(self.TAGGER_PRESETS[self.tagger_kind.get()])

    def start_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.start, self.logbox.log)

    def stop_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.stop, self.logbox.log)

    def _apply_backend_choices(self, choices):
        self.checkpoint_combo.configure(values=choices["checkpoints"])
        self.sampler_combo.configure(values=choices["samplers"])

    def _load_local_backend_choices(self):
        choices, _ = load_backend_choices(query_api=False)
        self._apply_backend_choices(choices)

    def refresh_backend_choices(self):
        def worker():
            choices, warnings = load_backend_choices(self.api_img2img.get(), query_api=True)
            self.after(0, lambda: self._finish_backend_refresh(choices, warnings))
        threading.Thread(target=worker, daemon=True).start()
        self.logbox.log("🔄 モデル候補をフォルダとAPIから更新中...")

    def _finish_backend_refresh(self, choices, warnings):
        self._apply_backend_choices(choices)
        self.logbox.log(
            f"✅ 候補更新: checkpoint {len(choices['checkpoints'])} / "
            f"sampler {len(choices['samplers'])}"
        )
        for warning in warnings:
            self.logbox.log(f"⚠️ API候補: {warning}")

    @staticmethod
    def _split(s): return [x.strip() for x in s.split(",") if x.strip()]
    @staticmethod
    def _compose_prompt(additional, manual_prompt, tags):
        return ", ".join([*additional, *( [manual_prompt.strip()] if manual_prompt.strip() else []), *tags])
    def start(self): self.stop_event.clear(); _safe_thread(self.logbox,self.run)
    def stop(self): self.stop_event.set(); self.logbox.log("停止要求を送信しました")
    def run(self):
        import base64, secrets, requests
        root=Path(self.input_dir.get().strip()); out=Path(self.output_dir.get().strip()); out.mkdir(parents=True,exist_ok=True)
        images=[p for p in root.rglob("*") if p.suffix.lower() in [".png",".jpg",".jpeg",".webp"]]
        if not images: self.logbox.log(f"画像が見つかりません: {root}"); return
        add=self._split(self.additional.get()); exc=set(self._split(self.exclude.get()))
        self.logbox.log(f"Found {len(images)} image(s)")
        for i in range(int(self.loops.get())):
            if self.stop_event.is_set(): break
            try:
                img=secrets.choice(images); self.logbox.log(f"[{i+1}] {img.name}")
                b64=base64.b64encode(img.read_bytes()).decode("utf-8")
                tags=[]
                if self.use_tagger.get():
                    tagger_url=self.api_interrogate.get().rstrip("/"); tagger_payload={"image":b64,"threshold":float(self.threshold.get())}
                    if "/pixai/v1/" in tagger_url: tagger_payload.update({"model":PIXAI_TAGGER_MODEL,"character_threshold":float(self.character_threshold.get())})
                    res=requests.post(tagger_url,json=tagger_payload,timeout=300); res.raise_for_status()
                    tags=[t for t in extract_tagger_tags(res.json()) if t not in exc and t.replace(" ","_") not in exc]
                prompt=self._compose_prompt(add, self.manual_prompt.get(), tags)
                if not prompt: raise ValueError("Taggerをオフにする場合は手動プロンプトまたは追加タグを入力してください")
                self.logbox.log(f"Prompt: {prompt}")
                if RUNTIME_BACKEND == "comfyui":
                    image_bytes = ComfyUIClient(self.api_img2img.get(), 10000).img2img(
                        image_path=img,
                        prompt=prompt,
                        negative=self.negative.get(),
                        checkpoint=self.checkpoint.get(),
                        steps=int(self.steps.get()),
                        cfg=float(self.cfg.get()),
                        sampler=self.sampler.get(),
                        denoise=float(self.denoise.get()),
                        width=int(self.width.get()),
                        height=int(self.height.get()),
                        stop_event=self.stop_event,
                    )
                else:
                    payload={"prompt":prompt,"negative_prompt":self.negative.get(),"init_images":[b64],"steps":int(self.steps.get()),"cfg_scale":float(self.cfg.get()),"width":int(self.width.get()),"height":int(self.height.get()),"denoising_strength":float(self.denoise.get()),"sampler_index":self.sampler.get(),"override_settings":{"sd_model_checkpoint":self.checkpoint.get()}}
                    rr=requests.post(self.api_img2img.get(),json=payload,timeout=10000); rr.raise_for_status()
                    data=rr.json().get("images",[])
                    image_bytes=base64.b64decode(data[0]) if data else None
                if image_bytes:
                    op=out/f"image_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.png"; op.write_bytes(image_bytes); self.logbox.log(f"✅ {op}")
                for _ in range(150):
                    if self.stop_event.is_set(): break
                    time.sleep(0.2)
            except Exception as e: self.logbox.log(f"❌ Error: {e}")
        self.logbox.log("終了")
