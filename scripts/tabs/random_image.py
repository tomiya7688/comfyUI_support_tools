from ..context import *
from ..context import _safe_thread
from ..context import _unique_choices
from ..services import *
from ..widgets.preset_store import PresetStore

class RandomImageTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.mod = EMBEDDED_RANDOM_IMAGE
        self.preset_store = PresetStore("random_image")
        self._queue: queue.Queue[str] = queue.Queue()
        self._build()
        self._load_defaults()
        self._attach_backend_logger()
        self._load_local_backend_choices()
        self.after(100, self._poll)

    def _build(self):
        if isinstance(self.mod, Exception):
            ttk.Label(self, text=f"random_image_creater_gui.py を読み込めませんでした: {self.mod}").pack(anchor="w")
            return

        self.var_input_file = tk.StringVar()
        self.var_negative_input_file = tk.StringVar()
        self.var_wildcard_root_dir = tk.StringVar()
        self.var_output_dir = tk.StringVar()
        self.var_api_url = tk.StringVar()
        self.var_width = tk.IntVar()
        self.var_height = tk.IntVar()
        self.var_steps = tk.IntVar()
        self.var_enable_hr = tk.BooleanVar()
        self.var_hr_scale = tk.DoubleVar()
        self.var_hr_upscaler = tk.StringVar()
        self.var_hr_second_pass_steps = tk.IntVar()
        self.var_denoising_strength = tk.DoubleVar()
        self.var_sampler_index = tk.StringVar()
        self.var_sd_model_checkpoint = tk.StringVar()
        self.var_use_model_vae = tk.BooleanVar(value=True)
        self.var_save_prompts = tk.BooleanVar(value=False)
        self.var_prompt_output = tk.StringVar()
        self.var_sequential_loop = tk.BooleanVar(value=False)
        self.var_sequential_reuse_wildcards = tk.BooleanVar(value=True)
        self.var_output_format = tk.StringVar(value="png")
        self.var_api_timeout = tk.IntVar()
        self.var_comfy_flow = tk.StringVar()
        self.var_preset_name = tk.StringVar()
        self.var_additional_position = tk.StringVar(value="prefix")
        self.var_wildcard_cache_scope = tk.StringVar(value="each_image")
        self.var_enable_nsfw_mosaic = tk.BooleanVar(value=False)
        self.var_nsfw_mosaic_factor = tk.IntVar(value=5)
        self.var_enable_failure_isolation = tk.BooleanVar(value=False)
        self.var_image_failure_min_variance = tk.DoubleVar(value=8.0)
        self.additional_file_rows = []
        self.action_wildcard_rows = []
        self.flow_model_vars = []

        top = ttk.LabelFrame(self, text="ファイル", padding=8)
        top.pack(fill="x")
        LabeledPathRow(top, "wildcard root", self.var_wildcard_root_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(top, "wildcard", self.var_input_file, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        LabeledPathRow(top, "negative wildcard", self.var_negative_input_file, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        LabeledPathRow(top, "出力先", self.var_output_dir, mode="dir").pack(fill="x", pady=3)
        ttk.Checkbutton(top, text="生成プロンプトを保存", variable=self.var_save_prompts).pack(anchor="w", pady=(4, 0))
        LabeledPathRow(top, "prompt保存先（txt/フォルダ）", self.var_prompt_output, mode="file", filetypes=[("Text", "*.txt"), ("All", "*.*")]).pack(fill="x", pady=3)
        api_row = ttk.Frame(top)
        api_row.pack(fill="x", pady=3)
        ttk.Label(api_row, text="API URL", width=16).pack(side="left", padx=(0, 6))
        ttk.Entry(api_row, textvariable=self.var_api_url).pack(side="left", fill="x", expand=True)

        wildcard_options = ttk.LabelFrame(self, text="追加ワイルドカード", padding=8)
        wildcard_options.pack(fill="x", pady=6)
        self.additional_files_frame = ttk.Frame(wildcard_options)
        self.additional_files_frame.pack(fill="x")
        ttk.Button(wildcard_options, text="追加ファイルを増やす", command=self._add_additional_file_row).pack(anchor="w", pady=(4, 0))
        self._add_additional_file_row()

        actions = ttk.LabelFrame(self, text="Action wildcard（展開後Promptのタグ条件で追加）", padding=8)
        actions.pack(fill="x", pady=6)
        self.action_wildcards_frame = ttk.Frame(actions)
        self.action_wildcards_frame.pack(fill="x")
        ttk.Button(actions, text="Actionを増やす", command=self._add_action_wildcard_row).pack(anchor="w", pady=(4, 0))
        self._add_action_wildcard_row()

        settings = ttk.LabelFrame(self, text="生成設定", padding=8)
        settings.pack(fill="x", pady=6)
        pairs = [
            ("幅", self.var_width), ("高さ", self.var_height), ("steps", self.var_steps),
            ("hr_scale", self.var_hr_scale), ("2nd pass", self.var_hr_second_pass_steps),
            ("denoise", self.var_denoising_strength), ("timeout(s)", self.var_api_timeout),
        ]
        for i, (label, var) in enumerate(pairs):
            r, c = divmod(i, 4)
            ttk.Label(settings, text=label).grid(row=r, column=c*2, sticky="w", padx=4, pady=3)
            ttk.Entry(settings, textvariable=var, width=10).grid(row=r, column=c*2+1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(settings, text="hires fix", variable=self.var_enable_hr).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(settings, text="upscaler").grid(row=2, column=2, sticky="w")
        self.upscaler_combo = ttk.Combobox(settings, textvariable=self.var_hr_upscaler, width=28)
        self.upscaler_combo.grid(row=2, column=3, columnspan=2, sticky="we")
        ttk.Label(settings, text="sampler").grid(row=3, column=0, sticky="w")
        self.sampler_combo = ttk.Combobox(settings, textvariable=self.var_sampler_index, width=18)
        self.sampler_combo.grid(row=3, column=1, sticky="w")
        ttk.Label(settings, text="checkpoint / UNet").grid(row=3, column=2, sticky="w")
        self.checkpoint_combo = ttk.Combobox(settings, textvariable=self.var_sd_model_checkpoint, width=40)
        self.checkpoint_combo.grid(row=3, column=3, columnspan=5, sticky="we")
        ttk.Checkbutton(settings, text="モデル付属VAEを使う", variable=self.var_use_model_vae).grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(settings, text="出力形式").grid(row=4, column=3, sticky="w")
        ttk.Combobox(settings, textvariable=self.var_output_format, values=["png", "webp", "jpg", "gif"], state="readonly", width=10).grid(row=4, column=4, sticky="w")
        if RUNTIME_BACKEND == "comfyui":
            ttk.Label(settings, text="Comfyフロー").grid(row=5, column=0, sticky="w")
            self.flow_combo = ttk.Combobox(settings, textvariable=self.var_comfy_flow, width=40)
            self.flow_combo.grid(row=5, column=1, columnspan=7, sticky="we")
            self.flow_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_flow_model_choices())
            self.flow_models_frame = ttk.LabelFrame(self, text="フロー固有モデル", padding=6)
            self.flow_models_frame.pack(fill="x", pady=4)

        mosaic = ttk.LabelFrame(self, text="NSFWモザイク（WebUI1111）", padding=8)
        mosaic.pack(fill="x", pady=6)
        ttk.Checkbutton(mosaic, text="NudeNetで検出した領域にモザイクを適用", variable=self.var_enable_nsfw_mosaic).pack(side="left")
        ttk.Label(mosaic, text="強度").pack(side="left", padx=(18, 4))
        ttk.Spinbox(mosaic, from_=1, to=10, textvariable=self.var_nsfw_mosaic_factor, width=5).pack(side="left")

        isolation = ttk.LabelFrame(self, text="画像破綻隔離（保守的な単色化検出）", padding=8)
        isolation.pack(fill="x", pady=6)
        ttk.Checkbutton(isolation, text="極端に単色な生成結果を _image_failure へ隔離", variable=self.var_enable_failure_isolation).pack(side="left")
        ttk.Label(isolation, text="最小分散").pack(side="left", padx=(18, 4))
        ttk.Entry(isolation, textvariable=self.var_image_failure_min_variance, width=7).pack(side="left")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="1枚生成", command=self.one).pack(side="left", padx=4)
        ttk.Button(buttons, text="無限生成", command=self.infinite).pack(side="left", padx=4)
        ttk.Button(buttons, text="順次生成", command=self.sequential).pack(side="left", padx=4)
        ttk.Checkbutton(buttons, text="順次を無限ループ", variable=self.var_sequential_loop).pack(side="left", padx=4)
        ttk.Checkbutton(buttons, text="順次中のWildcardを固定", variable=self.var_sequential_reuse_wildcards).pack(side="left", padx=4)
        ttk.Button(buttons, text="実行中へ設定を反映", command=self.update_running_generation).pack(side="left", padx=4)
        ttk.Button(buttons, text="停止", command=self.stop).pack(side="left", padx=4)
        ttk.Button(buttons, text="モデル候補更新", command=self.refresh_backend_choices).pack(side="left", padx=12)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.var_preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    def _load_defaults(self):
        if isinstance(self.mod, Exception):
            return
        self.var_input_file.set(getattr(self.mod, "input_file"))
        self.var_negative_input_file.set(getattr(self.mod, "negative_input_file"))
        self.var_wildcard_root_dir.set(getattr(self.mod, "wildcard_root_dir", self.mod.root_dir))
        self.var_output_dir.set(getattr(self.mod, "output_dir"))
        self.var_api_url.set(getattr(self.mod, "api_url"))
        self.var_width.set(getattr(self.mod, "width"))
        self.var_height.set(getattr(self.mod, "height"))
        self.var_steps.set(getattr(self.mod, "steps"))
        self.var_enable_hr.set(getattr(self.mod, "enable_hr"))
        self.var_hr_scale.set(getattr(self.mod, "hr_scale"))
        self.var_hr_upscaler.set(getattr(self.mod, "hr_upscaler"))
        self.var_hr_second_pass_steps.set(getattr(self.mod, "hr_second_pass_steps"))
        self.var_denoising_strength.set(getattr(self.mod, "denoising_strength"))
        self.var_sampler_index.set(getattr(self.mod, "sampler_index"))
        self.var_sd_model_checkpoint.set(getattr(self.mod, "sd_model_checkpoint"))
        self.var_use_model_vae.set(getattr(self.mod, "use_model_vae", True))
        self.var_save_prompts.set(getattr(self.mod, "save_prompts", False))
        self.var_prompt_output.set(getattr(self.mod, "prompt_output", ""))
        self.var_sequential_loop.set(getattr(self.mod, "sequential_loop", False))
        self.var_sequential_reuse_wildcards.set(getattr(self.mod, "sequential_reuse_wildcards", True))
        self.var_output_format.set(getattr(self.mod, "output_format", "png"))
        self.var_api_timeout.set(getattr(self.mod, "api_timeout"))
        self.var_comfy_flow.set(getattr(self.mod, "comfy_flow", ""))
        self.var_additional_position.set(getattr(self.mod, "additional_position", "prefix"))
        self.var_wildcard_cache_scope.set(getattr(self.mod, "wildcard_cache_scope", "each_image"))
        self.var_enable_nsfw_mosaic.set(getattr(self.mod, "enable_nsfw_mosaic", False))
        self.var_nsfw_mosaic_factor.set(getattr(self.mod, "nsfw_mosaic_factor", 5))
        self.var_enable_failure_isolation.set(getattr(self.mod, "enable_failure_isolation", False))
        self.var_image_failure_min_variance.set(getattr(self.mod, "image_failure_min_variance", 8.0))
        self._set_additional_file_rows(getattr(self.mod, "additional_inputs", []) or getattr(self.mod, "additional_input_files", []))
        self._set_action_wildcard_rows(getattr(self.mod, "action_wildcards", []))
        self._apply_flow_model_choices()
        self._refresh_preset_choices()

    def _preset_values(self):
        return {"input_file": self.var_input_file.get(), "negative_input_file": self.var_negative_input_file.get(), "wildcard_root_dir": self.var_wildcard_root_dir.get(), "output_dir": self.var_output_dir.get(), "api_url": self.var_api_url.get(), "width": self.var_width.get(), "height": self.var_height.get(), "steps": self.var_steps.get(), "enable_hr": self.var_enable_hr.get(), "hr_scale": self.var_hr_scale.get(), "hr_upscaler": self.var_hr_upscaler.get(), "hr_second_pass_steps": self.var_hr_second_pass_steps.get(), "denoising_strength": self.var_denoising_strength.get(), "sampler_index": self.var_sampler_index.get(), "sd_model_checkpoint": self.var_sd_model_checkpoint.get(), "api_timeout": self.var_api_timeout.get(), "comfy_flow": self.var_comfy_flow.get(), "additional_position": self.var_additional_position.get(), "wildcard_cache_scope": self.var_wildcard_cache_scope.get(), "additional_files": self._additional_specs(), "action_wildcards": self._action_wildcard_specs(), "enable_nsfw_mosaic": self.var_enable_nsfw_mosaic.get(), "nsfw_mosaic_factor": self.var_nsfw_mosaic_factor.get(), "enable_failure_isolation": self.var_enable_failure_isolation.get(), "image_failure_min_variance": self.var_image_failure_min_variance.get(), "flow_model_overrides": {key: variable.get() for key, _, variable in self.flow_model_vars}}

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            values = self._preset_values()
            values["use_model_vae"] = self.var_use_model_vae.get()
            values["save_prompts"] = self.var_save_prompts.get()
            values["prompt_output"] = self.var_prompt_output.get()
            values["sequential_loop"] = self.var_sequential_loop.get()
            values["sequential_reuse_wildcards"] = self.var_sequential_reuse_wildcards.get()
            values["output_format"] = self.var_output_format.get()
            path = self.preset_store.save(self.var_preset_name.get(), values)
            self.var_preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.var_preset_name.get())
            for key, variable in (("input_file", self.var_input_file), ("negative_input_file", self.var_negative_input_file), ("wildcard_root_dir", self.var_wildcard_root_dir), ("output_dir", self.var_output_dir), ("api_url", self.var_api_url), ("width", self.var_width), ("height", self.var_height), ("steps", self.var_steps), ("enable_hr", self.var_enable_hr), ("hr_scale", self.var_hr_scale), ("hr_upscaler", self.var_hr_upscaler), ("hr_second_pass_steps", self.var_hr_second_pass_steps), ("denoising_strength", self.var_denoising_strength), ("sampler_index", self.var_sampler_index), ("sd_model_checkpoint", self.var_sd_model_checkpoint), ("api_timeout", self.var_api_timeout), ("comfy_flow", self.var_comfy_flow), ("additional_position", self.var_additional_position), ("wildcard_cache_scope", self.var_wildcard_cache_scope), ("enable_nsfw_mosaic", self.var_enable_nsfw_mosaic), ("nsfw_mosaic_factor", self.var_nsfw_mosaic_factor), ("enable_failure_isolation", self.var_enable_failure_isolation), ("image_failure_min_variance", self.var_image_failure_min_variance)):
                if key in values: variable.set(values[key])
            self._set_additional_file_rows(values.get("additional_files", [])); self._set_action_wildcard_rows(values.get("action_wildcards", [])); self._apply_flow_model_choices(values.get("flow_model_overrides", {})); self.var_use_model_vae.set(values.get("use_model_vae", True)); self.logbox.log("プリセットを読み込みました")
            self.var_save_prompts.set(values.get("save_prompts", False)); self.var_prompt_output.set(values.get("prompt_output", ""))
            self.var_sequential_loop.set(values.get("sequential_loop", False))
            self.var_sequential_reuse_wildcards.set(values.get("sequential_reuse_wildcards", True))
            self.var_output_format.set(values.get("output_format", "png"))
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def _add_additional_file_row(self, value=None):
        value = value if isinstance(value, dict) else {"path": value or ""}
        row = ttk.LabelFrame(self.additional_files_frame, text="追加ワイルドカード", padding=4)
        row.pack(fill="x", pady=2)
        path = tk.StringVar(value=value.get("path", ""))
        label = tk.StringVar(value=value.get("label", ""))
        position = tk.StringVar(value=value.get("position", self.var_additional_position.get()))
        cache_scope = tk.StringVar(value=value.get("cache_scope", self.var_wildcard_cache_scope.get()))
        LabeledPathRow(row, "ファイル", path, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x")
        settings = ttk.Frame(row); settings.pack(fill="x", pady=(3, 0))
        ttk.Label(settings, text="用途メモ").pack(side="left"); ttk.Entry(settings, textvariable=label, width=18).pack(side="left", padx=(4, 12))
        ttk.Label(settings, text="位置").pack(side="left"); ttk.Combobox(settings, textvariable=position, values=["prefix", "suffix"], state="readonly", width=8).pack(side="left", padx=4)
        ttk.Label(settings, text="抽選").pack(side="left", padx=(8, 0)); ttk.Combobox(settings, textvariable=cache_scope, values=["each_image", "until_stop"], state="readonly", width=13).pack(side="left", padx=4)
        item = {"row": row, "path": path, "label": label, "position": position, "cache_scope": cache_scope}
        ttk.Button(settings, text="削除", command=lambda: self._remove_additional_file_row(item)).pack(side="right")
        self.additional_file_rows.append(item)

    def _remove_additional_file_row(self, item):
        item["row"].destroy()
        self.additional_file_rows = [current for current in self.additional_file_rows if current is not item]
        if not self.additional_file_rows:
            self._add_additional_file_row()

    def _additional_specs(self):
        return [{key: item[key].get() for key in ("path", "label", "position", "cache_scope")} for item in self.additional_file_rows]

    def _set_additional_file_rows(self, values):
        for item in self.additional_file_rows:
            item["row"].destroy()
        self.additional_file_rows = []
        for value in values:
            self._add_additional_file_row(value)
        if not self.additional_file_rows:
            self._add_additional_file_row()

    def _add_action_wildcard_row(self, value=None):
        value = value or {}
        row = ttk.LabelFrame(self.action_wildcards_frame, text="Action", padding=4)
        row.pack(fill="x", pady=2)
        condition = tk.StringVar(value=value.get("condition", ""))
        path = tk.StringVar(value=value.get("path", ""))
        position = tk.StringVar(value=value.get("position", "suffix"))
        cache_scope = tk.StringVar(value=value.get("cache_scope", "each_image"))
        fields = ttk.Frame(row); fields.pack(fill="x")
        ttk.Label(fields, text="条件タグ（,=AND / |=OR）").pack(side="left"); ttk.Entry(fields, textvariable=condition, width=24).pack(side="left", padx=(4, 10))
        ttk.Label(fields, text="位置").pack(side="left"); ttk.Combobox(fields, textvariable=position, values=["prefix", "suffix"], state="readonly", width=8).pack(side="left", padx=4)
        ttk.Label(fields, text="抽選").pack(side="left", padx=(8, 0)); ttk.Combobox(fields, textvariable=cache_scope, values=["each_image", "until_stop"], state="readonly", width=13).pack(side="left", padx=4)
        LabeledPathRow(row, "追加 wildcard", path, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=(3, 0))
        item = {"row": row, "condition": condition, "path": path, "position": position, "cache_scope": cache_scope}
        ttk.Button(fields, text="削除", command=lambda: self._remove_action_wildcard_row(item)).pack(side="right")
        self.action_wildcard_rows.append(item)

    def _remove_action_wildcard_row(self, item):
        item["row"].destroy()
        self.action_wildcard_rows = [current for current in self.action_wildcard_rows if current is not item]
        if not self.action_wildcard_rows:
            self._add_action_wildcard_row()

    def _action_wildcard_specs(self):
        return [{key: item[key].get() for key in ("condition", "path", "position", "cache_scope")} for item in self.action_wildcard_rows]

    def _set_action_wildcard_rows(self, values):
        for item in self.action_wildcard_rows:
            item["row"].destroy()
        self.action_wildcard_rows = []
        for value in values:
            self._add_action_wildcard_row(value)
        if not self.action_wildcard_rows:
            self._add_action_wildcard_row()

    def _apply_flow_model_choices(self, values=None):
        if not hasattr(self, "flow_models_frame"):
            return
        for child in self.flow_models_frame.winfo_children():
            child.destroy()
        self.flow_model_vars = []
        flow_name = self.var_comfy_flow.get().strip()
        if not flow_name:
            ttk.Label(self.flow_models_frame, text="Comfyフローを選ぶと、フロー内のモデル入力を表示します。").pack(anchor="w")
            return
        try:
            fields = ComfyUIClient.model_inputs(COMFY_FLOWS_DIR / flow_name)
        except (OSError, ValueError, KeyError) as error:
            ttk.Label(self.flow_models_frame, text=f"フロー読込エラー: {error}").pack(anchor="w")
            return
        base_choices, _ = load_backend_choices(query_api=False)
        choices = base_choices["checkpoints"]
        for field in fields:
            value = (values or {}).get(field["id"], field["value"])
            variable = tk.StringVar(value=value)
            row = ttk.Frame(self.flow_models_frame); row.pack(fill="x", pady=2)
            ttk.Label(row, text=field["label"], width=36).pack(side="left")
            ttk.Combobox(row, textvariable=variable, values=_unique_choices([field["value"], *choices]), width=55).pack(side="left", fill="x", expand=True)
            self.flow_model_vars.append((field["id"], field["label"], variable))
        if not fields:
            ttk.Label(self.flow_models_frame, text="モデル入力は検出されませんでした。").pack(anchor="w")

    def _attach_backend_logger(self):
        if isinstance(self.mod, Exception):
            return
        def tab_log(msg: str):
            self._queue.put(str(msg))
        self.mod._log = tab_log
        self.logbox.log("画像生成タブを起動しました")

    def _apply_backend_choices(self, choices):
        self.checkpoint_combo.configure(values=choices["checkpoints"])
        self.upscaler_combo.configure(values=choices["upscalers"])
        self.sampler_combo.configure(values=choices["samplers"])
        if hasattr(self, "flow_combo"):
            self.flow_combo.configure(values=choices.get("flows", []))
            self._apply_flow_model_choices()

    def _load_local_backend_choices(self):
        if isinstance(self.mod, Exception):
            return
        choices, _ = load_backend_choices(query_api=False)
        self._apply_backend_choices(choices)

    def refresh_backend_choices(self):
        def worker():
            choices, warnings = load_backend_choices(self.var_api_url.get(), query_api=True)
            self.after(0, lambda: self._finish_backend_refresh(choices, warnings))
        threading.Thread(target=worker, daemon=True).start()
        self.logbox.log("🔄 モデル候補をフォルダとAPIから更新中...")

    def _finish_backend_refresh(self, choices, warnings):
        self._apply_backend_choices(choices)
        self.logbox.log(
            f"✅ 候補更新: checkpoint {len(choices['checkpoints'])} / "
            f"upscaler {len(choices['upscalers'])} / sampler {len(choices['samplers'])}"
        )
        for warning in warnings:
            self.logbox.log(f"⚠️ API候補: {warning}")

    def _settings_from_gui(self):
        input_file = self.var_input_file.get().strip()
        wildcard_root_dir = self.var_wildcard_root_dir.get().strip()
        if not wildcard_root_dir:
            wildcard_root_dir = os.path.dirname(os.path.abspath(input_file))
            self.var_wildcard_root_dir.set(wildcard_root_dir)
        if not os.path.isdir(wildcard_root_dir):
            raise ValueError(f"wildcard rootディレクトリが存在しません: {wildcard_root_dir}")
        additional_inputs = [{**item, "path": item["path"].strip()} for item in self._additional_specs() if item["path"].strip()]
        return {
            "input_file": input_file, "negative_input_file": self.var_negative_input_file.get().strip(),
            "wildcard_root_dir": wildcard_root_dir, "root_dir": wildcard_root_dir,
            "output_dir": self.var_output_dir.get().strip(), "api_url": self.var_api_url.get().strip().rstrip("/"),
            "width": self.var_width.get(), "height": self.var_height.get(), "steps": self.var_steps.get(),
            "enable_hr": self.var_enable_hr.get(), "hr_scale": self.var_hr_scale.get(),
            "hr_upscaler": self.var_hr_upscaler.get(), "hr_second_pass_steps": self.var_hr_second_pass_steps.get(),
            "denoising_strength": self.var_denoising_strength.get(), "sampler_index": self.var_sampler_index.get(),
            "sd_model_checkpoint": self.var_sd_model_checkpoint.get(), "use_model_vae": self.var_use_model_vae.get(),
            "save_prompts": self.var_save_prompts.get(), "prompt_output": self.var_prompt_output.get().strip(),
            "sequential_loop": self.var_sequential_loop.get(), "sequential_reuse_wildcards": self.var_sequential_reuse_wildcards.get(), "output_format": self.var_output_format.get(),
            "api_timeout": self.var_api_timeout.get(),
            "comfy_flow": self.var_comfy_flow.get().strip() if RUNTIME_BACKEND == "comfyui" else "",
            "comfy_model_overrides": {key: variable.get().strip() for key, _, variable in self.flow_model_vars if variable.get().strip()},
            "additional_inputs": additional_inputs, "additional_input_files": [item["path"] for item in additional_inputs],
            "action_wildcards": [{**item, "condition": item["condition"].strip(), "path": item["path"].strip()} for item in self._action_wildcard_specs() if item["condition"].strip() and item["path"].strip()],
            "additional_position": self.var_additional_position.get(), "wildcard_cache_scope": self.var_wildcard_cache_scope.get(),
            "enable_nsfw_mosaic": self.var_enable_nsfw_mosaic.get(), "nsfw_mosaic_factor": self.var_nsfw_mosaic_factor.get(),
            "enable_failure_isolation": self.var_enable_failure_isolation.get(), "image_failure_min_variance": self.var_image_failure_min_variance.get(),
        }

    def _sync(self):
        for key, value in self._settings_from_gui().items():
            setattr(self.mod, key, value)

    def update_running_generation(self):
        try:
            self.mod.queue_settings_update(self._settings_from_gui())
            self.logbox.log("🔄 現在の1枚が終わった後、次の生成から設定を反映します")
        except Exception as e:
            self.logbox.log(f"設定更新エラー: {e}")

    def one(self):
        try:
            self._sync()
            self.mod._start_thread("once")
        except Exception as e:
            self.logbox.log(f"エラー: {e}")

    def infinite(self):
        try:
            self._sync()
            self.mod._start_thread("infinite")
        except Exception as e:
            self.logbox.log(f"エラー: {e}")

    def sequential(self):
        try:
            self._sync()
            self.mod._start_thread("sequential")
        except Exception as e:
            self.logbox.log(f"エラー: {e}")

    def stop(self):
        try:
            self.mod._stop()
        except Exception as e:
            self.logbox.log(f"エラー: {e}")

    def _poll(self):
        if not isinstance(self.mod, Exception):
            while not self._queue.empty():
                self.logbox.log(self._queue.get())
        self.after(100, self._poll)
