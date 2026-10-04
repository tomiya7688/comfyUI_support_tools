from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore
from ..backend.image_to_image_request import ImageToImageRequest
from ..backend.image_generation_backend_factory import create_image_generation_backend
from ..backend.model_choice_classification import (
    classify_base_model_choice,
    describe_model_classification,
)
from ..backend.prompt_lora_compatibility import validate_prompt_loras

# {
#   "責務": "フォルダ画像にTaggerを適用し、ランダムpromptでimg2img生成する。",
#   "フィールド": ["input/output/Tagger/API/model/生成設定: UI状態", "generator: 生成backend", "stop_event: 停止要求", "preset_store/preset_name: preset状態", "model_choices: model catalog", "logbox: 実行結果"]
# }
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
    # {
    #   "責務": "img2imgタブのgenerator、入力状態、候補一覧とUIを初期化する。",
    #   "処理": ["生成backendから初期値を読み各種UI変数を作る", "画面を構築する"],
    #   "引数": {"master": "親Tk widget"}, "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.stop_event=threading.Event()
        self._active_backend=None
        self.model_choices = {"checkpoints": [], "unets": [], "loras": [], "vaes": []}
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
        self.steps=tk.StringVar(value="25"); self.cfg=tk.StringVar(value="6.5"); self.width=tk.StringVar(value="960"); self.height=tk.StringVar(value="1280"); self.denoise=tk.StringVar(value="0.75"); self.sampler=tk.StringVar(value="Euler a"); self.checkpoint=tk.StringVar(value="shiitakeMix_v20.safetensors" if RUNTIME_BACKEND == "comfyui" else "rinIllusionRNSFW_v20"); self.vae_name=tk.StringVar(); self.loops=tk.StringVar(value="100000")
        LabeledPathRow(self,"INPUT_DIR",self.input_dir,mode="dir").pack(fill="x",pady=2); LabeledPathRow(self,"OUTPUT_DIR",self.output_dir,mode="dir").pack(fill="x",pady=2)
        tagger_row=ttk.Frame(self); tagger_row.pack(fill="x",pady=2); ttk.Checkbutton(tagger_row,text="Taggerで入力画像からタグを取得",variable=self.use_tagger).pack(side="left"); ttk.Label(tagger_row,text="TAGGER",width=12).pack(side="left"); tagger_combo=ttk.Combobox(tagger_row,textvariable=self.tagger_kind,values=list(self.TAGGER_PRESETS),state="readonly",width=24); tagger_combo.pack(side="left"); tagger_combo.bind("<<ComboboxSelected>>",self._apply_tagger_preset); ttk.Button(tagger_row,text="PixAI API起動",command=self.start_pixai_api).pack(side="left",padx=(12,4)); ttk.Button(tagger_row,text="PixAI API停止",command=self.stop_pixai_api).pack(side="left",padx=4)
        for label,var in [("API_INTERROGATE",self.api_interrogate),("API_IMG2IMG",self.api_img2img),("手動プロンプト（Taggerなし時）",self.manual_prompt),("ADDITIONAL_TAGS",self.additional)]:
            r=ttk.Frame(self); r.pack(fill="x",pady=2); ttk.Label(r,text=label,width=22).pack(side="left"); ttk.Entry(r,textvariable=var).pack(side="left",fill="x",expand=True)
        grid=ttk.Frame(self); grid.pack(fill="x",pady=4)
        for i,(label,var) in enumerate([("THRESHOLD",self.threshold),("CHAR_THRESHOLD",self.character_threshold),("STEPS",self.steps),("CFG",self.cfg),("WIDTH",self.width),("HEIGHT",self.height),("DENOISE",self.denoise),("SAMPLER",self.sampler),("CHECKPOINT",self.checkpoint),("VAE",self.vae_name),("LOOPS",self.loops)]):
            r,c=divmod(i,3); ttk.Label(grid,text=label).grid(row=r,column=c*2,sticky="w")
            widget = ttk.Combobox(grid,textvariable=var,width=20) if label in {"SAMPLER","CHECKPOINT","VAE"} else ttk.Entry(grid,textvariable=var,width=20)
            widget.grid(row=r,column=c*2+1,sticky="we",padx=3)
            if label == "SAMPLER": self.sampler_combo = widget
            if label == "CHECKPOINT": self.checkpoint_combo = widget
            if label == "VAE": self.vae_combo = widget
        self.model_classification_text = tk.StringVar(value="モデルを選ぶと系統判定と根拠を表示します。")
        ttk.Label(grid, textvariable=self.model_classification_text, wraplength=900).grid(
            row=4, column=0, columnspan=6, sticky="w", padx=3, pady=(2, 4)
        )
        self.checkpoint.trace_add("write", self._update_model_classification)
        btn=ttk.Frame(self); btn.pack(fill="x"); ttk.Button(btn,text="開始",command=self.start).pack(side="left",padx=4); ttk.Button(btn,text="停止",command=self.stop).pack(side="left",padx=4); ttk.Button(btn,text="モデル候補更新",command=self.refresh_backend_choices).pack(side="left",padx=12); ttk.Label(btn,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(btn,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(btn,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(btn,text="読込",command=self.load_preset).pack(side="left",padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
        self.logbox.log("※ 生成中にAPIエラーが出てもGUIは継続します。")
        if RUNTIME_BACKEND == "comfyui":
            self.logbox.log("※ タグ取得にはPixAI API（7861）、生成にはComfyUI API（8188）を使います。")
        self._load_local_backend_choices()
        self._refresh_preset_choices()

    # {
    #   "責務": "現在のimg2img設定をpreset用dictへまとめる。",
    #   "処理": ["入出力、Tagger、生成条件、model選択値を読み取る"],
    #   "引数": [], "戻り値": "preset保存用dict"
    # }
    def _preset_values(self):
        values = {key: variable.get() for key, variable in (("input_dir",self.input_dir),("output_dir",self.output_dir),("tagger_kind",self.tagger_kind),("api_interrogate",self.api_interrogate),("api_img2img",self.api_img2img),("threshold",self.threshold),("character_threshold",self.character_threshold),("additional",self.additional),("manual_prompt",self.manual_prompt),("exclude",self.exclude),("negative",self.negative),("steps",self.steps),("cfg",self.cfg),("width",self.width),("height",self.height),("denoise",self.denoise),("sampler",self.sampler),("checkpoint",self.checkpoint),("vae_name",self.vae_name),("loops",self.loops))}
        values["use_tagger"] = self.use_tagger.get()
        return values

    # {
    #   "責務": "保存済みpreset名で選択widgetを更新する。",
    #   "処理": ["PresetStoreのname一覧をcomboboxへ設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "現在のimg2img設定を名前付きpresetに保存する。",
    #   "処理": ["設定値を保存し候補を更新する", "結果をlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def save_preset(self):
        try:
            path=self.preset_store.save(self.preset_name.get(),self._preset_values()); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択presetからimg2imgのUI状態を復元する。",
    #   "処理": ["保存済み設定を変数へ適用する", "成功またはエラーをlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def load_preset(self):
        try:
            values=self.preset_store.load(self.preset_name.get())
            for key,variable in (("input_dir",self.input_dir),("output_dir",self.output_dir),("tagger_kind",self.tagger_kind),("api_interrogate",self.api_interrogate),("api_img2img",self.api_img2img),("threshold",self.threshold),("character_threshold",self.character_threshold),("additional",self.additional),("manual_prompt",self.manual_prompt),("exclude",self.exclude),("negative",self.negative),("steps",self.steps),("cfg",self.cfg),("width",self.width),("height",self.height),("denoise",self.denoise),("sampler",self.sampler),("checkpoint",self.checkpoint),("vae_name",self.vae_name),("loops",self.loops)):
                if key in values: variable.set(values[key])
            self.use_tagger.set(values.get("use_tagger", True))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "選択Taggerの既定endpoint/modelを反映する。",
    #   "処理": ["TAGGER_PRESETSからURLとmodelを取得しUI変数を更新する"],
    #   "引数": {"_event": "combobox event。省略可"}, "戻り値": []
    # }
    def _apply_tagger_preset(self, _event=None):
        self.api_interrogate.set(self.TAGGER_PRESETS[self.tagger_kind.get()])

    # {
    #   "責務": "PixAI Tagger serverの起動を非同期依頼する。",
    #   "処理": ["共通thread helperでserver.startを実行する"],
    #   "引数": [], "戻り値": []
    # }
    def start_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.start, self.logbox.log)

    # {
    #   "責務": "PixAI Tagger serverの停止を非同期依頼する。",
    #   "処理": ["共通thread helperでserver.stopを実行する"],
    #   "引数": [], "戻り値": []
    # }
    def stop_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.stop, self.logbox.log)

    # {
    #   "責務": "backend model候補を選択widgetと分類表示へ反映する。",
    #   "処理": ["checkpoint/UNet/LoRA/VAE catalogを保持する", "選択widgetと系統分類を更新する"],
    #   "引数": {"choices": "backend model choices"}, "戻り値": []
    # }
    def _apply_backend_choices(self, choices):
        self.model_choices = {
            "checkpoints": list(choices.get("checkpoints", [])),
            "unets": list(choices.get("unets", [])),
            "loras": list(choices.get("loras", [])),
            "vaes": list(choices.get("vaes", [])),
        }
        self.checkpoint_combo.configure(values=base_model_choices(choices))
        self._update_model_classification()
        self.sampler_combo.configure(values=choices["samplers"])
        self.vae_combo.configure(values=choices.get("vaes", []))

    # {
    #   "責務": "選択base modelのfamily分類説明をUIへ反映する。",
    #   "処理": ["未選択なら案内を表示する", "model catalogで分類して説明を表示する"],
    #   "引数": {"_args": "trace callback引数"}, "戻り値": []
    # }
    def _update_model_classification(self, *_args):
        selected = self.checkpoint.get().strip()
        if not selected:
            self.model_classification_text.set("モデルを選ぶと系統判定と根拠を表示します。")
            return
        classification = classify_base_model_choice(selected, self.model_choices)
        self.model_classification_text.set(describe_model_classification(classification))

    # {
    #   "責務": "ローカルbackend catalogを読んで選択肢を初期化する。",
    #   "処理": ["API照会なしで候補一覧をロードする", "choicesをwidgetへ適用する"],
    #   "引数": [], "戻り値": []
    # }
    def _load_local_backend_choices(self):
        choices, _ = load_backend_choices(query_api=False)
        self._apply_backend_choices(choices)

    # {
    #   "責務": "backend APIを使う候補一覧更新をworkerで始める。",
    #   "処理": ["取得workerをdaemon起動する", "更新中の状態をlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def refresh_backend_choices(self):
        # {
        #   "責務": "backend APIからmodel候補を取得してGUI threadへ反映を予約する。",
        #   "処理": ["API照会付き候補ロードを行う", "候補とwarningをafter callbackに渡す"],
        #   "引数": [], "戻り値": []
        # }
        def worker():
            choices, warnings = load_backend_choices(self.api_img2img.get(), query_api=True)
            self.after(0, lambda: self._finish_backend_refresh(choices, warnings))
        threading.Thread(target=worker, daemon=True).start()
        self.logbox.log("🔄 モデル候補をフォルダとAPIから更新中...")

    # {
    #   "責務": "取得済みbackend候補とwarningを適用・表示する。",
    #   "処理": ["choicesをUIへ適用する", "件数とwarningをlogへ出す"],
    #   "引数": {"choices": "候補dict", "warnings": "警告list"}, "戻り値": []
    # }
    def _finish_backend_refresh(self, choices, warnings):
        self._apply_backend_choices(choices)
        self.logbox.log(
            f"✅ 候補更新: checkpoint {len(choices['checkpoints'])} / "
            f"UNet {len(choices.get('unets', []))} / LoRA {len(choices.get('loras', []))} / "
            f"sampler {len(choices['samplers'])}"
        )
        for warning in warnings:
            self.logbox.log(f"⚠️ API候補: {warning}")

    # {
    #   "責務": "カンマ区切り文字列から空でないtagを抽出する。",
    #   "処理": ["区切りで分割しstrip後の空文字を除外する"],
    #   "引数": {"s": "tag列"}, "戻り値": "tag list"
    # }
    @staticmethod
    def _split(s): return [x.strip() for x in s.split(",") if x.strip()]
    # {
    #   "責務": "追加prompt、手入力prompt、tagを一つのpositive promptへ結合する。",
    #   "処理": ["空要素を除き指定順でcomma joinする"],
    #   "引数": {"additional": "prefix tags", "manual_prompt": "手入力文", "tags": "自動tag list"}, "戻り値": "結合prompt"
    # }
    @staticmethod
    def _compose_prompt(additional, manual_prompt, tags):
        return ", ".join([*additional, *( [manual_prompt.strip()] if manual_prompt.strip() else []), *tags])
    # {
    #   "責務": "停止flagを解除しimg2img処理を安全threadで開始する。",
    #   "処理": ["stop eventをclearしsafe thread helperでrunする"],
    #   "引数": [], "戻り値": []
    # }
    def start(self): self.stop_event.clear(); _safe_thread(self.logbox,self.run)
    # {
    #   "責務": "img2img workerへ停止要求を伝える。",
    #   "処理": ["stop eventをsetしlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def stop(self):
        self.stop_event.set()
        backend=self._active_backend
        if backend is not None and backend.capabilities.supports("interrupt"):
            _safe_thread(self.logbox,backend.interrupt)
        self.logbox.log("停止要求を送信しました")
    # {
    #   "責務": "入力folderの画像へtag抽出とprompt構築を行いimg2img生成する。",
    #   "処理": ["入力と設定を検証する", "各画像をtaggerへ送りpromptと生成条件を適用する", "停止要求を確認し進捗を記録する"],
    #   "引数": [], "戻り値": []
    # }
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
                validate_prompt_loras(prompt, self.checkpoint.get(), self.model_choices, self.logbox.log)
                backend = create_image_generation_backend(
                    RUNTIME_BACKEND,
                    self.api_img2img.get(),
                    10000,
                    request_post=requests.post,
                )
                self._active_backend=backend
                try:
                    image_bytes = backend.generate_from_image(
                        ImageToImageRequest(
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
                        vae_name=self.vae_name.get(),
                        ),
                        stop_event=self.stop_event,
                    )
                finally:
                    if self._active_backend is backend:
                        self._active_backend=None
                if image_bytes:
                    op=out/f"image_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.png"; op.write_bytes(image_bytes); self.logbox.log(f"✅ {op}")
                for _ in range(150):
                    if self.stop_event.is_set(): break
                    time.sleep(0.2)
            except Exception as e: self.logbox.log(f"❌ Error: {e}")
        self.logbox.log("終了")
