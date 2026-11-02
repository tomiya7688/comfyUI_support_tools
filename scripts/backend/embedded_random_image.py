import io
import json
import re

from PIL import Image

from comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings
from comfyui_support_tools.shared.contracts.resolved_generation_parameters import (
    ResolvedGenerationParameters,
)
from comfyui_support_tools.shared.prompt_stability.analyzer import PromptRiskAnalyzer
from comfyui_support_tools.shared.prompt_stability.contracts import (
    ApplyMode,
    ComputeBudget,
    ContentMode,
    GuardSettings,
    IntentPreservation,
    PromptRiskRequest,
    RiskTolerance,
)
from comfyui_support_tools.shared.prompt_stability.planner import PromptAdjustmentPlanner

from ..context import *
from .generation_parameter_resolver import GenerationParameterResolver
from .image_failure_inspector import ImageFailureInspector
from .ollama_prompt_corrector import OllamaPromptCorrector
from .prompt_lora_compatibility import validate_prompt_loras
from .text_to_image_request import TextToImageRequest

_GENERATION_PROFILE = create_configured_image_generation_profile(datetime.now().strftime("%Y%m%d"))

# {
#   責務: [EmbeddedRandomImage: wildcard promptから画像生成要求を組み立てて保存する]
#   フィールド: [generation_profile: backend選択に基づく生成既定値, api_url: API接続先, output_dir: 画像保存先, sd_model_checkpoint: 既定checkpoint]
#   処理: [promptと生成設定を共通形式へ変換し, backend adapterへ渡す]
# }
class EmbeddedRandomImage:
    input_file = str(WILDCARDS_DIR / "random_batch_nsfw_hub.txt")
    negative_input_file = str(WILDCARDS_DIR / "all_negative.txt")
    wildcard_root_dir = os.path.dirname(input_file)
    generation_profile = _GENERATION_PROFILE
    output_dir = str(generation_profile.output_dir)
    api_url = generation_profile.api_url
    api_timeout = 10000
    width, height, steps = 960, 1280, 25
    enable_hr, hr_scale = False, 1.5
    hr_upscaler, hr_second_pass_steps = "R-ESRGAN 4x+ Anime6B", 20
    denoising_strength = 0.7
    sampler_index = "Euler a"
    sd_model_checkpoint = generation_profile.default_checkpoint
    comfy_flow = ""
    additional_input_files = []
    additional_inputs = []
    action_wildcards = []
    additional_position = "prefix"
    wildcard_cache_scope = "each_image"
    enable_nsfw_mosaic = False
    nsfw_mosaic_factor = 5
    enable_failure_isolation = False
    image_failure_min_variance = 8.0
    comfy_model_overrides = {}
    model_catalog = {"checkpoints": [], "unets": [], "loras": []}
    generation_parameter_config = None
    use_model_vae = True
    vae_name = ""
    save_prompts = False
    prompt_output = ""
    sequential_loop = False
    sequential_reuse_wildcards = True
    output_format = "png"
    enable_prompt_correction = False
    prompt_guard_enabled = False
    prompt_guard_mode = "sfw"
    prompt_guard_sfw = True
    prompt_guard_nsfw = True
    prompt_guard_apply_mode = "suggest_only"
    prompt_guard_budget = "standard"
    prompt_guard_preview = True
    prompt_guard_intent = "strict"
    prompt_guard_tolerance = "balanced"
    ollama_api_url = "http://127.0.0.1:11434"
    ollama_model = ""

    def __init__(self):
        self.root_dir = self.wildcard_root_dir
        self.additional_input_files = list(self.additional_input_files)
        self.additional_inputs = [dict(item) for item in self.additional_inputs]
        self.action_wildcards = [dict(item) for item in self.action_wildcards]
        self.comfy_model_overrides = dict(self.comfy_model_overrides)
        self.model_catalog = {key: list(value) for key, value in self.model_catalog.items()}
        self._stop_event = threading.Event()
        self._active_backend = None
        self._worker_thread = None
        self._settings_lock = threading.Lock()
        self._pending_settings = None
        self._log = print

    # {
    #   責務: [queue_settings_update: 実行中workerへ次の画像用設定を予約する]
    #   処理: [Random Image設定IDを確認し, FeatureSettings snapshotをlock下で保存する]
    #   引数: [self: generator instance, settings: generation.random_image設定]
    #   戻り値: []
    #   エラー: [TypeError: FeatureSettings以外の場合, ValueError: feature IDが一致しない場合]
    # }
    def queue_settings_update(self, settings: FeatureSettings):
        """Stage settings so a running worker applies them before its next image."""
        if not isinstance(settings, FeatureSettings):
            raise TypeError("settings must be FeatureSettings")
        if settings.feature_id != "generation.random_image":
            raise ValueError(f"unsupported settings feature: {settings.feature_id}")
        with self._settings_lock:
            self._pending_settings = settings

    # {
    #   責務: [_apply_pending_settings: workerが予約済み設定snapshotを適用する]
    #   処理: [lock下でsnapshotを取り出し, 各設定値をgeneratorへ適用する]
    #   引数: [self: generator instance]
    #   戻り値: [bool: 設定適用の有無]
    # }
    def _apply_pending_settings(self):
        with self._settings_lock:
            settings = self._pending_settings
            self._pending_settings = None
        if settings is None:
            return False
        for key, value in settings.values.items():
            setattr(self, key, value)
        self._log("🔄 次の生成へ設定更新を適用しました")
        return True

    def _select_source(self, rel_path, root=None):
        root = root or self.root_dir
        path = Path(rel_path) if os.path.isabs(rel_path) else Path(root) / rel_path
        if not path.exists() and path.suffix.lower() == ".txt":
            directory_candidate = path.with_suffix("")
            if directory_candidate.is_dir():
                path = directory_candidate
        if not path.is_dir():
            return path
        candidates = sorted((item for item in path.rglob("*.txt") if item.is_file()), key=lambda item: item.as_posix().casefold())
        if not candidates:
            self._log(f"⚠️ ワイルドカード用txtがありません: {path}")
            return None
        selected = secrets.choice(candidates)
        self._log(f"📁 ワイルドカードディレクトリから選択: {selected}")
        return selected

    def _read_lines(self, path):
        try:
            with open(path, encoding="utf-8") as source:
                return [line.strip() for line in source if line.strip()]
        except FileNotFoundError:
            self._log(f"⚠️ ファイルが見つかりません: {path}")
            return []

    def _expand_text(self, text, root, depth=0, wildcard_cache=None):
        pattern = re.compile(r"\{([^{}]+)\}")
        while pattern.search(text):
            match = pattern.search(text)
            text = text[:match.start()] + secrets.choice(match.group(1).split("|")) + text[match.end():]
        placeholders = {}
        text = re.sub(r"<[^>]*>", lambda match: placeholders.setdefault(f"__LORA_{len(placeholders)}__", match.group(0)), text)

        def expand_wildcard(match):
            name = match.group(1)
            if name.startswith("LORA_"):
                return match.group(0)
            return self.process_file(name.strip("_") + ".txt", root, depth + 1, wildcard_cache)

        text = re.sub(r"__(.*?)__", expand_wildcard, text)
        for key, value in placeholders.items():
            text = text.replace(key, value)
        return text

    def process_file(self, rel_path, root=None, depth=0, wildcard_cache=None):
        if depth > 50:
            return ""
        root = root or self.root_dir
        requested_path = rel_path if os.path.isabs(rel_path) else os.path.join(root, rel_path)
        cache_key = os.path.normcase(os.path.abspath(requested_path))
        if wildcard_cache is not None and cache_key in wildcard_cache:
            return wildcard_cache[cache_key]
        path = self._select_source(rel_path, root)
        if path is None:
            return ""
        lines = self._read_lines(path)
        if not lines:
            return ""
        text = secrets.choice(lines)
        text = self._expand_text(text, root, depth, wildcard_cache)
        if wildcard_cache is not None:
            wildcard_cache[cache_key] = text
        return text

    def _additional_entries(self):
        if self.additional_inputs:
            return [item for item in self.additional_inputs if item.get("path")]
        return [
            {"path": path, "label": "", "position": self.additional_position, "cache_scope": self.wildcard_cache_scope}
            for path in self.additional_input_files if path
        ]

    def _additional_prompts(self, wildcard_cache=None):
        prefix, suffix = [], []
        for item in self._additional_entries():
            cache = wildcard_cache if item.get("cache_scope") == "until_stop" else None
            part = self.process_file(item["path"], self.root_dir, wildcard_cache=cache)
            if not part:
                continue
            (suffix if item.get("position") == "suffix" else prefix).append(part)
        return prefix, suffix

    def _with_additional_prompt(self, prompt, wildcard_cache=None):
        prefix, suffix = self._additional_prompts(wildcard_cache)
        parts = [*prefix]
        if prompt:
            parts.append(prompt)
        parts.extend(suffix)
        return ", ".join(parts)

    @staticmethod
    def _action_condition_matches(condition, normalized_prompt):
        """`,` はAND、`|` はORとして展開済みプロンプトのタグを照合する。"""
        alternatives = [item.strip() for item in condition.split("|") if item.strip()]
        return any(all(tag.strip() in normalized_prompt for tag in item.split(",") if tag.strip()) for item in alternatives)

    def _with_action_prompt(self, prompt, wildcard_cache=None):
        prefix, suffix = [], []
        normalized_prompt = prompt.casefold().replace("_", " ")
        for action in self.action_wildcards:
            condition = str(action.get("condition", "")).strip().casefold().replace("_", " ")
            path = str(action.get("path", "")).strip()
            if not condition or not path or not self._action_condition_matches(condition, normalized_prompt):
                continue
            cache = wildcard_cache if action.get("cache_scope") == "until_stop" else None
            part = self.process_file(path, self.root_dir, wildcard_cache=cache)
            if part:
                (suffix if action.get("position") == "suffix" else prefix).append(part)
                self._log(f"⚡ Action wildcard: {condition} -> {path}")
        return ", ".join([*prefix, prompt, *suffix])

    # {
    #   責務: [_apply_nsfw_mosaic: backend capabilityに応じてNudeNetモザイクを適用する]
    #   処理: [1: 設定とadapter capabilityを確認する, 2: A1111 extensionへ画像を送り, 3: 加工画像または元画像を返す]
    #   引数: [self: モザイク設定と接続設定を持つgenerator, image_bytes: 生成画像bytes, backend: 使用中のgeneration adapter]
    #   戻り値: [bytes: モザイク後または元の画像bytes]
    # }
    def _apply_nsfw_mosaic(self, image_bytes, backend):
        if not self.enable_nsfw_mosaic:
            return image_bytes
        if not backend.capabilities.supports("nudenet_mosaic"):
            self._log("選択中のbackendはNudeNetモザイクに対応していないため、元画像を保存します")
            return image_bytes
        censor_url = re.sub(r"/sdapi/.*$", "", self.api_url.rstrip("/")) + "/nudenet/censor"
        payload = {
            "input_image": base64.b64encode(image_bytes).decode("ascii"),
            "enable_nudenet": True,
            "filter_type": "Pixelate",
            "pixelation_factor": self.nsfw_mosaic_factor,
            "mask_shape": "Ellipse",
            "mask_blend_radius": 0,
        }
        try:
            response = requests.post(censor_url, json=payload, timeout=self.api_timeout)
            response.raise_for_status()
            censored = response.json().get("image")
            if censored:
                self._log("NSFW検出領域へモザイクを適用しました")
                return base64.b64decode(censored)
            self._log("NSFWモザイク: 対象領域は検出されませんでした")
        except Exception as error:
            self._log(f"NSFWモザイクをスキップしました: {error}")
        return image_bytes

    def _save_failure_report(self, output, failure, prompt, negative, parameters):
        report_dir = USER_DATA_DIR / "output" / "image_generate" / "log" / "image_failure"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "output": str(output), "failure": failure, "backend": self.generation_profile.backend,
            "checkpoint": self.sd_model_checkpoint, "sampler": self.sampler_index,
            "width": self.width, "height": self.height, "steps": self.steps,
            "generation_parameters": parameters,
            "prompt": prompt, "negative_prompt": negative,
        }
        report_path = report_dir / f"{output.stem}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report_path

    def _resolve_generation_parameters(self):
        configuration = self.generation_parameter_config
        if configuration is None:
            configuration = {
                "cfg": {"mode": "fixed", "value": 7.0},
                "steps": {"mode": "fixed", "value": self.steps},
                "resolution": {
                    "mode": "fixed",
                    "value": {"width": self.width, "height": self.height},
                },
                "sampler": {"mode": "fixed", "value": self.sampler_index},
            }
        return GenerationParameterResolver().resolve(configuration)

    def _save_generation_metadata(self, image_path, parameters):
        metadata_path = image_path.with_suffix(".generation.json")
        metadata = {
            "backend": self.generation_profile.backend,
            "checkpoint": self.sd_model_checkpoint,
            **parameters,
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return metadata_path

    def _save_prompt(self, image_output, prompt):
        if not self.save_prompts or not self.prompt_output:
            return None
        destination = Path(self.prompt_output)
        if destination.suffix:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("a", encoding="utf-8") as target:
                target.write(prompt.strip() + "\n")
            return destination
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"{image_output.stem}.txt"
        target.write_text(prompt.strip() + "\n", encoding="utf-8")
        return target

    def _encoded_output(self, image_bytes):
        """Return generated image bytes in the format selected by the user."""
        image_format = str(self.output_format).lower()
        if image_format == "png":
            return image_bytes, "png"
        if image_format not in {"webp", "jpg", "gif"}:
            self._log(f"⚠️ 未対応の出力形式 {image_format!r} のためPNGで保存します")
            return image_bytes, "png"
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            buffer = io.BytesIO()
            if image_format == "webp":
                converted.save(buffer, format="WEBP", quality=95, method=6)
            elif image_format == "gif":
                converted.convert("P", palette=Image.Palette.ADAPTIVE, colors=256).save(buffer, format="GIF")
            else:
                converted.save(buffer, format="JPEG", quality=95, optimize=True)
        return buffer.getvalue(), image_format

    def _correct_prompt(self, prompt):
        """Correct the fully expanded prompt only when the user enabled Ollama."""
        if not self.enable_prompt_correction:
            return prompt
        corrected = OllamaPromptCorrector().correct(self.ollama_api_url, self.ollama_model, prompt, requests)
        self._log(f"🪄 Ollamaでプロンプトを補正しました: {corrected}")
        return corrected

    # {
    #   責務: [_generate: promptと設定snapshotから画像1枚を生成する]
    #   処理: [設定候補を解決済みparameter objectへ変換し, API backendへTextToImageRequestとして渡す]
    #   引数: [self: generator, prompt: 任意の展開済みprompt, negative: 任意のnegative prompt, wildcard_cache: wildcard結果cache]
    #   戻り値: []
    # }
    def _generate(self, prompt=None, negative=None, wildcard_cache=None):
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        if negative is None:
            negative = self.process_file(self.negative_input_file, self.root_dir, wildcard_cache=wildcard_cache) if self.negative_input_file else ""
        if prompt is None:
            prompt = self.process_file(self.input_file, self.root_dir, wildcard_cache=wildcard_cache)
        prompt = self._with_action_prompt(self._with_additional_prompt(prompt, wildcard_cache), wildcard_cache)
        prompt = self._correct_prompt(prompt)
        guard_mode = ContentMode(self.prompt_guard_mode)
        guard_settings = GuardSettings(
            enabled=bool(self.prompt_guard_enabled),
            apply_to_sfw=bool(self.prompt_guard_sfw),
            apply_to_nsfw=bool(self.prompt_guard_nsfw),
            apply_mode=ApplyMode(self.prompt_guard_apply_mode),
            budget=ComputeBudget(self.prompt_guard_budget),
            intent_preservation=IntentPreservation(self.prompt_guard_intent),
            risk_tolerance=RiskTolerance(self.prompt_guard_tolerance),
            show_preview=bool(self.prompt_guard_preview),
        )
        workflow_path = resolve_comfy_flow_path(self.comfy_flow) if self.comfy_flow else None
        backend = create_configured_image_generation_backend(self.api_url, self.api_timeout)
        backend.capabilities.require("txt2img")
        workflow_has_model_overrides = (
            backend.capabilities.supports("model_overrides")
            and bool(self.comfy_model_overrides)
        )
        validate_prompt_loras(
            prompt,
            None if workflow_has_model_overrides else self.sd_model_checkpoint,
            self.model_catalog,
            self._log,
            base_model_reason=(
                "The ComfyUI workflow has per-node model overrides; the LoRA's active base node is ambiguous."
                if workflow_has_model_overrides else None
            ),
        )
        parameters = self._resolve_generation_parameters()
        loras = tuple(
            (name, float(weight), "style" if "style" in name.casefold() else "pose" if "pose" in name.casefold() else "character" if "char" in name.casefold() else "")
            for name, weight in re.findall(r"<lora:([^:>]+):([0-9.]+)>", prompt, re.IGNORECASE)
        )
        risk_request = PromptRiskRequest(
            prompt=prompt,
            negative_prompt=negative,
            content_mode=guard_mode,
            settings=guard_settings,
            backend=self.generation_profile.backend,
            model=self.sd_model_checkpoint,
            loras=loras,
            parameters={"candidate_count": 1, "steps": parameters.steps, "cfg": parameters.cfg},
        )
        risk_report = PromptRiskAnalyzer().analyze(risk_request)
        plan = PromptAdjustmentPlanner().plan(risk_request, risk_report)
        if guard_settings.enabled:
            self._log(
                f"Prompt stability {risk_report.overall_risk.value} / {guard_mode.value}: "
                + (
                    ", ".join(factor.description for factor in risk_report.risk_factors)
                    or "no structural risk detected"
                )
            )
            for suggestion in risk_report.suggested_adjustments:
                self._log(f"Prompt stability suggestion: {suggestion}")
            if guard_settings.show_preview:
                self._log(
                    f"Prompt stability preview: candidates {plan.original_candidate_count} -> "
                    f"{plan.candidate_count}; {', '.join(plan.adjustment_log) or 'prompt unchanged'}"
                )
        if plan.applied:
            if guard_settings.show_preview and plan.adjusted_prompt != prompt:
                self._log(f"Prompt before: {prompt}\nPrompt after: {plan.adjusted_prompt}")
            if guard_settings.show_preview and plan.adjusted_negative_prompt != negative:
                self._log(
                    f"Negative prompt before: {negative}\n"
                    f"Negative prompt after: {plan.adjusted_negative_prompt}"
                )
            prompt = plan.adjusted_prompt
            negative = plan.adjusted_negative_prompt
            adjusted = dict(plan.adjusted_parameters)
            parameters = ResolvedGenerationParameters(
                cfg=float(adjusted.get("cfg", parameters.cfg)),
                steps=int(adjusted.get("steps", parameters.steps)),
                width=parameters.width,
                height=parameters.height,
                sampler=parameters.sampler,
                parameters=parameters.parameters,
                backend_parameters=parameters.backend_parameters,
            )
        self._log(
            "🎛️ 生成パラメータ: "
            f"CFG={parameters.cfg:g}, Steps={parameters.steps}, "
            f"Resolution={parameters.width}x{parameters.height}, "
            f"Sampler={parameters.sampler}"
        )
        if workflow_path and not backend.capabilities.supports("workflow"):
            raise ValueError("選択中の生成バックエンドはカスタムworkflowに対応していません")
        if self.enable_hr and not backend.capabilities.supports("hires_fix"):
            raise ValueError("選択中の生成バックエンドはHires Fixに対応していません")
        generation_request = TextToImageRequest(
            prompt=prompt,
            negative=negative,
            checkpoint=self.sd_model_checkpoint,
            steps=parameters.steps,
            cfg=parameters.cfg,
            sampler=parameters.sampler,
            width=parameters.width,
            height=parameters.height,
            use_model_vae=self.use_model_vae,
            vae_name=self.vae_name,
            enable_hr=self.enable_hr,
            hr_scale=self.hr_scale,
            hr_upscaler=self.hr_upscaler,
            hr_second_pass_steps=self.hr_second_pass_steps,
            denoising_strength=self.denoising_strength,
            workflow_path=workflow_path,
            model_overrides=self.comfy_model_overrides,
        )
        candidate_total = max(1, plan.candidate_count)
        attempt_limit = min(candidate_total, plan.retry_limit + 1) if plan.retry_limit else candidate_total
        for candidate_index in range(attempt_limit):
            if self._stop_event.is_set():
                break
            self._active_backend = backend
            try:
                image_bytes = backend.generate(generation_request, stop_event=self._stop_event)
            finally:
                if self._active_backend is backend:
                    self._active_backend = None
            if not image_bytes:
                continue
            image_bytes = self._apply_nsfw_mosaic(image_bytes, backend)
            image_bytes, output_extension = self._encoded_output(image_bytes)
            failure = None
            if self.enable_failure_isolation or plan.retry_limit:
                failure = ImageFailureInspector(self.image_failure_min_variance).inspect(image_bytes)
            if failure and plan.retry_limit:
                self._log(f"⚠️ stability retry {candidate_index + 1}/{attempt_limit}: {failure['reason']}")
                if candidate_index + 1 < attempt_limit:
                    continue
            output_dir = Path(self.output_dir)
            if failure:
                output_dir = output_dir / "_image_failure"
            output = output_dir / f"image_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{candidate_index + 1}.{output_extension}"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(image_bytes)
            metadata = parameters.to_dict()
            metadata["prompt_stability"] = {
                "content_mode": guard_mode.value,
                "risk": risk_report.overall_risk.value,
                "risk_factors": [factor.key for factor in risk_report.risk_factors],
                "candidate_index": candidate_index + 1,
                "candidate_count": candidate_total,
                "adjustments": list(plan.adjustment_log),
            }
            metadata_path = self._save_generation_metadata(output, metadata)
            prompt_path = self._save_prompt(output, prompt)
            if failure:
                report_path = self._save_failure_report(output, failure, prompt, negative, metadata)
                self._log(f"⚠️ 破綻候補を隔離しました: {output} / 記録: {report_path}")
            else:
                self._log(
                    f"✅ 生成成功 ({candidate_index + 1}/{candidate_total}): {output} / parameters: {metadata_path}"
                    + (f" / prompt: {prompt_path}" if prompt_path else "")
                )
            if plan.retry_limit and not failure:
                break

    def _sequential_prompt_sources(self):
        source = Path(self.input_file)
        if not source.is_absolute():
            source = Path(self.root_dir) / source
        if not source.exists() and source.suffix.lower() == ".txt" and source.with_suffix("").is_dir():
            source = source.with_suffix("")
        if source.is_file():
            return [source]
        if source.is_dir():
            return sorted((path for path in source.rglob("*.txt") if path.is_file()), key=lambda path: path.as_posix().casefold())
        return []

    def _generate_sequential(self):
        sources = self._sequential_prompt_sources()
        prompts = [(path, line) for path in sources for line in self._read_lines(path)]
        if not prompts:
            self._log("⚠️ 順次生成するプロンプトがありません。")
            return

        total = len(prompts)
        completed = 0
        self._log(f"▶️ 順次生成開始: {total}件" + "（無限ループ）" if self.sequential_loop else f"▶️ 順次生成開始: {total}件")
        while not self._stop_event.is_set():
            shared_wildcard_cache = {} if self.sequential_reuse_wildcards else None
            for index, (source_path, source_text) in enumerate(prompts, start=1):
                if self._stop_event.is_set(): break
                try:
                    self._apply_pending_settings()
                    prompt = self._expand_text(source_text, self.root_dir, wildcard_cache=shared_wildcard_cache)
                    try:
                        source_label = source_path.relative_to(self.root_dir).as_posix()
                    except ValueError:
                        source_label = str(source_path)
                    self._log(f"📝 [{index}/{total}] {source_label}: {prompt}")
                    self._generate(prompt=prompt, wildcard_cache=shared_wildcard_cache); completed += 1
                except Exception as e: self._log(f"❌ [{index}/{total}] 生成エラー: {e}")
            if not self.sequential_loop: break

        if self._stop_event.is_set():
            self._log(f"⏹️ 順次生成を停止しました: {completed}/{total}件完了")
        else:
            self._log(f"✅ 順次生成完了: {completed}/{total}件")

    def _start_thread(self, mode):
        if self._worker_thread and self._worker_thread.is_alive():
            self._log("実行中: すでに生成中です。停止してから開始してください。")
            return
        self._stop_event.clear()
        def worker():
            try:
                backend = create_configured_image_generation_backend(self.api_url, self.api_timeout)
                backend.capabilities.require("txt2img")
            except Exception as error:
                self._log(f"❌ 生成バックエンドを利用できません: {error}")
                return
            if mode == "sequential":
                self._generate_sequential()
                return
            shared_wildcard_cache = {} if self.wildcard_cache_scope == "until_stop" else None
            while not self._stop_event.is_set():
                try:
                    self._apply_pending_settings()
                    self._generate(wildcard_cache=shared_wildcard_cache)
                except Exception as e:
                    self._log(f"❌ 生成エラー: {e}")
                if mode == "once":
                    break
        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _stop(self):
        self._stop_event.set()
        backend = self._active_backend
        if backend is None or not backend.capabilities.supports("interrupt"):
            return
        threading.Thread(target=self._interrupt_backend, args=(backend,), daemon=True).start()

    def _interrupt_backend(self, backend):
        try:
            backend.interrupt()
            self._log("⏹️ 生成中断をバックエンドへ送信しました")
        except Exception as error:
            self._log(f"⚠️ バックエンド中断に失敗しました: {error}")
