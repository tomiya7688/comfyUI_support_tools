from __future__ import annotations

from ..context import *
from ..context import _unique_choices
from ..backend.model_choice_classification import (
    classify_base_model_choice,
    describe_model_classification,
)
from ..backend.prompt_lora_compatibility import (
    assess_prompt_loras,
    format_prompt_lora_findings,
)
from ..services import *
from ..widgets.preset_store import PresetStore


# {
#   "責務": "手入力promptをwildcard展開し生成backendへ送り、モデル選択互換情報を表示する。",
#   "フィールド": ["generator: 生成backend client", "wildcard_root/output_dir/api_url: pathと接続先", "prompt/negative UI: 入力文", "width/height/steps/sampler/checkpoint/vae/flow: 生成条件", "model_choices: model catalog", "preset_store/preset_name: preset", "logbox: 実行log"]
# }
class PromptGenerateTab(ttk.Frame):
    """手入力プロンプトを現在の生成バックエンドへ送る。"""

    # {
    #   "責務": "prompt generationタブの初期状態とbackend候補を準備する。",
    #   "処理": ["generatorから初期生成値を読みUI変数とpreset状態を作る", "画面を作りローカル候補を適用する"],
    #   "引数": {"master": "親Tk widget"}, "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.generator = EmbeddedRandomImage()
        self.generator._log = self._log_from_worker
        self.wildcard_root = tk.StringVar(value=str(WILDCARDS_DIR))
        self.output_dir = tk.StringVar(value=self.generator.output_dir)
        self.api_url = tk.StringVar(value=self.generator.api_url)
        self.width = tk.IntVar(value=self.generator.width)
        self.height = tk.IntVar(value=self.generator.height)
        self.steps = tk.IntVar(value=self.generator.steps)
        self.sampler = tk.StringVar(value=self.generator.sampler_index)
        self.checkpoint = tk.StringVar(value=self.generator.sd_model_checkpoint)
        self.vae_name = tk.StringVar(value=getattr(self.generator, "vae_name", ""))
        self.comfy_flow = tk.StringVar(value=self.generator.comfy_flow)
        self.preset_store = PresetStore("prompt_generate")
        self.preset_name = tk.StringVar()
        self.model_choices = {"checkpoints": [], "unets": [], "loras": [], "vaes": []}
        self._build()
        self._load_backend_choices()

    # {
    #   "責務": "prompt入力、生成設定、model互換情報、実行とpresetのUIを構築する。",
    #   "処理": ["pathとpositive/negative prompt欄を配置する", "生成条件・model選択・実行操作・logを配置する"],
    #   "引数": [], "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "wildcard root", self.wildcard_root, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "出力先", self.output_dir, mode="dir").pack(fill="x", pady=3)
        api_row = ttk.Frame(self)
        api_row.pack(fill="x", pady=3)
        ttk.Label(api_row, text="API URL", width=16).pack(side="left")
        ttk.Entry(api_row, textvariable=self.api_url).pack(side="left", fill="x", expand=True)

        prompt_frame = ttk.LabelFrame(self, text="Prompt（__wildcard__ / <lora:...> / {a|b} 対応）", padding=6)
        prompt_frame.pack(fill="both", expand=True, pady=(6, 3))
        self.prompt = ScrolledText(prompt_frame, height=7, wrap="word")
        self.prompt.pack(fill="both", expand=True)
        negative_frame = ttk.LabelFrame(self, text="Negative prompt", padding=6)
        negative_frame.pack(fill="both", expand=True, pady=3)
        self.negative = ScrolledText(negative_frame, height=4, wrap="word")
        self.negative.pack(fill="both", expand=True)
        lora_frame = ttk.LabelFrame(self, text="LoRA互換性（family-level）", padding=5)
        lora_frame.pack(fill="x", pady=(2, 4))
        self.lora_compatibility_text = tk.StringVar(value="LoRA指定はありません。")
        ttk.Label(lora_frame, textvariable=self.lora_compatibility_text, wraplength=900).pack(anchor="w")
        self.prompt.bind("<KeyRelease>", self._update_lora_compatibility)

        settings = ttk.Frame(self)
        settings.pack(fill="x", pady=4)
        for index, (label, variable) in enumerate((("幅", self.width), ("高さ", self.height), ("steps", self.steps))):
            ttk.Label(settings, text=label).grid(row=0, column=index * 2, sticky="w", padx=(0, 4))
            ttk.Entry(settings, textvariable=variable, width=8).grid(row=0, column=index * 2 + 1, sticky="w", padx=(0, 10))
        ttk.Label(settings, text="sampler").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.sampler_combo = ttk.Combobox(settings, textvariable=self.sampler, width=22)
        self.sampler_combo.grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(settings, text="checkpoint / UNet").grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.checkpoint_combo = ttk.Combobox(settings, textvariable=self.checkpoint, width=42)
        self.checkpoint_combo.grid(row=1, column=3, columnspan=3, sticky="we", pady=(4, 0))
        ttk.Label(settings, text="VAE（任意）").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.vae_combo = ttk.Combobox(settings, textvariable=self.vae_name, width=42)
        self.vae_combo.grid(row=2, column=1, columnspan=5, sticky="we", pady=(4, 0))
        self.model_classification_text = tk.StringVar(value="モデルを選ぶと系統判定と根拠を表示します。")
        ttk.Label(settings, textvariable=self.model_classification_text, wraplength=900).grid(
            row=4, column=0, columnspan=6, sticky="w", pady=(2, 0)
        )
        self.checkpoint.trace_add("write", self._update_model_classification)
        if RUNTIME_BACKEND == "comfyui":
            ttk.Label(settings, text="Comfyフロー").grid(row=3, column=0, sticky="w", pady=(4, 0))
            self.flow_combo = ttk.Combobox(settings, textvariable=self.comfy_flow, width=42)
            self.flow_combo.grid(row=3, column=1, columnspan=5, sticky="we", pady=(4, 0))
            self.flow_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_flow_checkpoint_choices())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="1枚生成", command=self.start).pack(side="left")
        ttk.Button(buttons, text="モデル候補更新", command=self.refresh_backend_choices).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    # {
    #   "責務": "worker由来のmessageをTk UI thread上でlogへ反映する。",
    #   "処理": ["after callbackを登録しmessageを文字列化して表示する"],
    #   "引数": {"message": "worker log message"}, "戻り値": []
    # }
    def _log_from_worker(self, message):
        self.after(0, lambda: self.logbox.log(str(message)))

    # {
    #   "責務": "positive prompt widgetの内容を取得する。",
    #   "処理": ["末尾改行を除いてText内容を読み取る"],
    #   "引数": [], "戻り値": "positive prompt文字列"
    # }
    def _prompt_text(self):
        return self.prompt.get("1.0", "end-1c")

    # {
    #   "責務": "negative prompt widgetの内容を取得する。",
    #   "処理": ["末尾改行を除いてText内容を読み取る"],
    #   "引数": [], "戻り値": "negative prompt文字列"
    # }
    def _negative_text(self):
        return self.negative.get("1.0", "end-1c")

    # {
    #   "責務": "Text widgetの既存内容を指定文字列へ置き換える。",
    #   "処理": ["全文を削除し先頭からvalueを挿入する"],
    #   "引数": {"widget": "編集対象Text widget", "value": "設定する文字列"}, "戻り値": []
    # }
    def _set_text(self, widget, value):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    # {
    #   "責務": "現在の生成設定とpromptをpreset保存dictへまとめる。",
    #   "処理": ["path・API・prompt・生成値・model・flow UI値を読み取る"],
    #   "引数": [], "戻り値": "preset保存用dict"
    # }
    def _preset_values(self):
        return {
            "wildcard_root": self.wildcard_root.get(), "output_dir": self.output_dir.get(), "api_url": self.api_url.get(),
            "prompt": self._prompt_text(), "negative": self._negative_text(), "width": self.width.get(), "height": self.height.get(),
            "steps": self.steps.get(), "sampler": self.sampler.get(), "checkpoint": self.checkpoint.get(), "vae_name": self.vae_name.get(), "comfy_flow": self.comfy_flow.get(),
        }

    # {
    #   "責務": "preset storeにある名前を選択widgetへ反映する。",
    #   "処理": ["保存済みname一覧をcombobox候補に設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "現在のprompt生成設定を名前付きpresetとして保存する。",
    #   "処理": ["UI状態を保存し選択名・候補を更新する", "成否をlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values())
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択された生成presetの設定をUIへ復元する。",
    #   "処理": ["値とprompt本文を復元する", "flow候補・LoRA互換表示を更新する"],
    #   "引数": [], "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("wildcard_root", self.wildcard_root), ("output_dir", self.output_dir), ("api_url", self.api_url), ("width", self.width), ("height", self.height), ("steps", self.steps), ("sampler", self.sampler), ("checkpoint", self.checkpoint), ("vae_name", self.vae_name), ("comfy_flow", self.comfy_flow)):
                if key in values:
                    variable.set(values[key])
            self._set_text(self.prompt, values.get("prompt", self._prompt_text()))
            self._set_text(self.negative, values.get("negative", self._negative_text()))
            self._apply_flow_checkpoint_choices()
            self._update_lora_compatibility()
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "API照会なしのローカルbackend候補を読み込みUIへ適用する。",
    #   "処理": ["load_backend_choicesをquery_api=Falseで呼び出す", "候補を_apply_backend_choicesへ渡す"],
    #   "引数": [], "戻り値": []
    # }
    def _load_backend_choices(self):
        choices, _ = load_backend_choices(query_api=False)
        self._apply_backend_choices(choices)

    # {
    #   "責務": "backend model/sampler/flow候補を選択widgetと互換表示へ反映する。",
    #   "処理": ["model catalogを保存する", "選択widgetと分類/LoRA説明を更新する"],
    #   "引数": {"choices": "backend候補dict"}, "戻り値": []
    # }
    def _apply_backend_choices(self, choices):
        self.model_choices = {
            "checkpoints": list(choices.get("checkpoints", [])),
            "unets": list(choices.get("unets", [])),
            "loras": list(choices.get("loras", [])),
            "vaes": list(choices.get("vaes", [])),
        }
        self.sampler_combo.configure(values=choices["samplers"])
        self.checkpoint_combo.configure(values=base_model_choices(choices))
        self.vae_combo.configure(values=choices.get("vaes", []))
        self._update_model_classification()
        self._update_lora_compatibility()
        if hasattr(self, "flow_combo"):
            self.flow_combo.configure(values=choices.get("flows", []))
            self._apply_flow_checkpoint_choices()

    # {
    #   "責務": "選択flowに対応するcheckpoint候補をcheckpoint widgetへ追加する。",
    #   "処理": ["flowを調べmodel choiceと重複しない候補を設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _apply_flow_checkpoint_choices(self):
        if not hasattr(self, "flow_combo"):
            return
        choices = flow_checkpoint_choices(self.comfy_flow.get())
        if choices:
            self.checkpoint_combo.configure(values=_unique_choices(choices + list(self.checkpoint_combo.cget("values"))))

    # {
    #   "責務": "選択checkpointの系統分類と根拠を表示する。",
    #   "処理": ["未選択なら案内を表示する", "model catalogで分類しLoRA互換表示を再計算する"],
    #   "引数": {"_args": "trace callback引数"}, "戻り値": []
    # }
    def _update_model_classification(self, *_args):
        selected = self.checkpoint.get().strip()
        if not selected:
            self.model_classification_text.set("モデルを選ぶと系統判定と根拠を表示します。")
            self._update_lora_compatibility()
            return
        classification = classify_base_model_choice(selected, self.model_choices)
        self.model_classification_text.set(describe_model_classification(classification))
        self._update_lora_compatibility()

    # {
    #   "責務": "prompt内LoRAとcheckpointのfamily互換診断を表示する。",
    #   "処理": ["prompt text/model catalogを診断器へ渡し整形結果を更新する"],
    #   "引数": {"_event": "UI event。省略可"}, "戻り値": []
    # }
    def _update_lora_compatibility(self, _event=None):
        findings = assess_prompt_loras(
            self._prompt_text(), self.checkpoint.get(), self.model_choices
        )
        self.lora_compatibility_text.set(format_prompt_lora_findings(findings))

    # {
    #   "責務": "backend API照会による候補更新を非同期で開始する。",
    #   "処理": ["workerを起動して更新中logを出す"],
    #   "引数": [], "戻り値": []
    # }
    def refresh_backend_choices(self):
        # {
        #   "責務": "backend APIから候補を取得してUI threadへ完了処理を予約する。",
        #   "処理": ["load_backend_choicesをquery_api=Trueで実行する", "候補とwarningをafter経由で反映する"],
        #   "引数": [], "戻り値": []
        # }
        def worker():
            choices, warnings = load_backend_choices(self.api_url.get(), query_api=True)
            self.after(0, lambda: self._finish_backend_refresh(choices, warnings))
        threading.Thread(target=worker, daemon=True).start()
        self.logbox.log("モデル候補を更新中...")

    # {
    #   "責務": "API取得済み候補とwarningをUIへ反映し結果をlogする。",
    #   "処理": ["候補を適用する", "件数とwarningをlogへ出す"],
    #   "引数": {"choices": "backend候補dict", "warnings": "取得時warning一覧"}, "戻り値": []
    # }
    def _finish_backend_refresh(self, choices, warnings):
        self._apply_backend_choices(choices)
        self.logbox.log(
            f"候補更新: checkpoint {len(choices['checkpoints'])} / "
            f"UNet {len(choices.get('unets', []))} / LoRA {len(choices.get('loras', []))} / "
            f"sampler {len(choices['samplers'])}"
        )
        for warning in warnings:
            self.logbox.log(f"API候補: {warning}")

    # {
    #   "責務": "prompt生成処理を安全なworker threadで開始する。",
    #   "処理": ["safe thread helperからrunを実行する"],
    #   "引数": [], "戻り値": []
    # }
    def start(self):
        _safe_thread(self.logbox, self.run)

    # {
    #   "責務": "promptと設定を検証・wildcard展開し生成backendへ1枚生成を依頼する。",
    #   "処理": ["wildcard root/promptを検証する", "generatorへ設定を転送しpromptを展開する", "生成処理へpositive/negativeと共有wildcard cacheを渡す"],
    #   "引数": [], "戻り値": []
    # }
    def run(self):
        root = Path(self.wildcard_root.get().strip())
        if not root.is_dir():
            raise ValueError(f"wildcard rootディレクトリが存在しません: {root}")
        source_prompt = self._prompt_text().strip()
        if not source_prompt:
            raise ValueError("Promptを入力してください")
        self.generator.root_dir = str(root)
        self.generator.wildcard_root_dir = str(root)
        self.generator.output_dir = self.output_dir.get().strip()
        self.generator.api_url = self.api_url.get().strip().rstrip("/")
        self.generator.width = self.width.get()
        self.generator.height = self.height.get()
        self.generator.steps = self.steps.get()
        self.generator.sampler_index = self.sampler.get()
        self.generator.sd_model_checkpoint = self.checkpoint.get()
        self.generator.vae_name = self.vae_name.get()
        self.generator.model_catalog = {
            key: list(self.model_choices.get(key, []))
            for key in ("checkpoints", "unets", "loras", "vaes")
        }
        self.generator.comfy_flow = self.comfy_flow.get()
        cache = {}
        prompt = self.generator._expand_text(source_prompt, self.generator.root_dir, wildcard_cache=cache)
        negative = self.generator._expand_text(self._negative_text(), self.generator.root_dir, wildcard_cache=cache)
        self.logbox.log(f"展開済み prompt: {prompt}")
        self.generator._generate(prompt=prompt, negative=negative, wildcard_cache=cache)
