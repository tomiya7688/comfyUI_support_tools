from __future__ import annotations

from ..context import *
from ..services import *
from ..widgets.preset_store import PresetStore


class PromptGenerateTab(ttk.Frame):
    """手入力プロンプトを現在の生成バックエンドへ送る。"""

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
        self.comfy_flow = tk.StringVar(value=self.generator.comfy_flow)
        self.preset_store = PresetStore("prompt_generate")
        self.preset_name = tk.StringVar()
        self._build()
        self._load_backend_choices()

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
        if RUNTIME_BACKEND == "comfyui":
            ttk.Label(settings, text="Comfyフロー").grid(row=2, column=0, sticky="w", pady=(4, 0))
            self.flow_combo = ttk.Combobox(settings, textvariable=self.comfy_flow, width=42)
            self.flow_combo.grid(row=2, column=1, columnspan=5, sticky="we", pady=(4, 0))
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

    def _log_from_worker(self, message):
        self.after(0, lambda: self.logbox.log(str(message)))

    def _prompt_text(self):
        return self.prompt.get("1.0", "end-1c")

    def _negative_text(self):
        return self.negative.get("1.0", "end-1c")

    def _set_text(self, widget, value):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _preset_values(self):
        return {
            "wildcard_root": self.wildcard_root.get(), "output_dir": self.output_dir.get(), "api_url": self.api_url.get(),
            "prompt": self._prompt_text(), "negative": self._negative_text(), "width": self.width.get(), "height": self.height.get(),
            "steps": self.steps.get(), "sampler": self.sampler.get(), "checkpoint": self.checkpoint.get(), "comfy_flow": self.comfy_flow.get(),
        }

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values())
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("wildcard_root", self.wildcard_root), ("output_dir", self.output_dir), ("api_url", self.api_url), ("width", self.width), ("height", self.height), ("steps", self.steps), ("sampler", self.sampler), ("checkpoint", self.checkpoint), ("comfy_flow", self.comfy_flow)):
                if key in values:
                    variable.set(values[key])
            self._set_text(self.prompt, values.get("prompt", self._prompt_text()))
            self._set_text(self.negative, values.get("negative", self._negative_text()))
            self._apply_flow_checkpoint_choices()
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def _load_backend_choices(self):
        choices, _ = load_backend_choices(query_api=False)
        self._apply_backend_choices(choices)

    def _apply_backend_choices(self, choices):
        self.sampler_combo.configure(values=choices["samplers"])
        self.checkpoint_combo.configure(values=choices["checkpoints"])
        if hasattr(self, "flow_combo"):
            self.flow_combo.configure(values=choices.get("flows", []))
            self._apply_flow_checkpoint_choices()

    def _apply_flow_checkpoint_choices(self):
        if not hasattr(self, "flow_combo"):
            return
        choices = flow_checkpoint_choices(self.comfy_flow.get())
        if choices:
            self.checkpoint_combo.configure(values=_unique_choices(choices + list(self.checkpoint_combo.cget("values"))))

    def refresh_backend_choices(self):
        def worker():
            choices, warnings = load_backend_choices(self.api_url.get(), query_api=True)
            self.after(0, lambda: self._finish_backend_refresh(choices, warnings))
        threading.Thread(target=worker, daemon=True).start()
        self.logbox.log("モデル候補を更新中...")

    def _finish_backend_refresh(self, choices, warnings):
        self._apply_backend_choices(choices)
        self.logbox.log(f"候補更新: checkpoint {len(choices['checkpoints'])} / sampler {len(choices['samplers'])}")
        for warning in warnings:
            self.logbox.log(f"API候補: {warning}")

    def start(self):
        _safe_thread(self.logbox, self.run)

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
        self.generator.comfy_flow = self.comfy_flow.get()
        cache = {}
        prompt = self.generator._expand_text(source_prompt, self.generator.root_dir, wildcard_cache=cache)
        negative = self.generator._expand_text(self._negative_text(), self.generator.root_dir, wildcard_cache=cache)
        self.logbox.log(f"展開済み prompt: {prompt}")
        self.generator._generate(prompt=prompt, negative=negative, wildcard_cache=cache)
