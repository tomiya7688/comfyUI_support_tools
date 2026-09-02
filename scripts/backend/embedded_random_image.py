from ..context import *
import io
from PIL import Image
from .comfy_ui_client import ComfyUIClient
from .image_failure_inspector import ImageFailureInspector

class EmbeddedRandomImage:
    input_file = str(WILDCARDS_DIR / "random_batch_nsfw_hub.txt")
    negative_input_file = str(WILDCARDS_DIR / "all_negative.txt")
    wildcard_root_dir = os.path.dirname(input_file)
    output_dir = str(
        (RUNTIME_DIR / "output" / "KadokaTools" if RUNTIME_BACKEND == "comfyui"
         else A1111_DIR / "outputs" / "txt2img-images")
        / datetime.now().strftime("%Y%m%d")
    )
    api_url = (
        "http://127.0.0.1:8188"
        if RUNTIME_BACKEND == "comfyui"
        else "http://127.0.0.1:7860/sdapi/v1/txt2img"
    )
    api_timeout = 10000
    width, height, steps = 960, 1280, 25
    enable_hr, hr_scale = False, 1.5
    hr_upscaler, hr_second_pass_steps = "R-ESRGAN 4x+ Anime6B", 20
    denoising_strength = 0.7
    sampler_index = "Euler a"
    sd_model_checkpoint = (
        "shiitakeMix_v20.safetensors"
        if RUNTIME_BACKEND == "comfyui"
        else "rinIllusionRNSFW_v30"
    )
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
    use_model_vae = True
    save_prompts = False
    prompt_output = ""
    sequential_loop = False
    output_format = "png"

    def __init__(self):
        self.root_dir = self.wildcard_root_dir
        self.additional_input_files = list(self.additional_input_files)
        self.additional_inputs = [dict(item) for item in self.additional_inputs]
        self.action_wildcards = [dict(item) for item in self.action_wildcards]
        self.comfy_model_overrides = dict(self.comfy_model_overrides)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._log = print

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

    def _apply_nsfw_mosaic(self, image_bytes):
        if not self.enable_nsfw_mosaic:
            return image_bytes
        if RUNTIME_BACKEND != "a1111":
            self._log("NSFWモザイクはWebUI1111のNudeNet拡張が必要なため、元画像を保存します")
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

    def _save_failure_report(self, output, failure, prompt, negative):
        report_dir = USER_DATA_DIR / "output" / "image_generate" / "log" / "image_failure"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "output": str(output), "failure": failure, "backend": RUNTIME_BACKEND,
            "checkpoint": self.sd_model_checkpoint, "sampler": self.sampler_index,
            "width": self.width, "height": self.height, "steps": self.steps,
            "prompt": prompt, "negative_prompt": negative,
        }
        report_path = report_dir / f"{output.stem}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report_path

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
        if image_format not in {"webp", "jpg"}:
            self._log(f"⚠️ 未対応の出力形式 {image_format!r} のためPNGで保存します")
            return image_bytes, "png"
        with Image.open(io.BytesIO(image_bytes)) as image:
            converted = image.convert("RGB")
            buffer = io.BytesIO()
            if image_format == "webp":
                converted.save(buffer, format="WEBP", quality=95, method=6)
            else:
                converted.save(buffer, format="JPEG", quality=95, optimize=True)
        return buffer.getvalue(), image_format

    def _generate(self, prompt=None, negative=None, wildcard_cache=None):
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        if negative is None:
            negative = self.process_file(self.negative_input_file, self.root_dir, wildcard_cache=wildcard_cache) if self.negative_input_file else ""
        if prompt is None:
            prompt = self.process_file(self.input_file, self.root_dir, wildcard_cache=wildcard_cache)
        prompt = self._with_action_prompt(self._with_additional_prompt(prompt, wildcard_cache), wildcard_cache)
        image_bytes = None
        if RUNTIME_BACKEND == "comfyui":
            image_bytes = ComfyUIClient(self.api_url, self.api_timeout).txt2img(
                prompt=prompt,
                negative=negative,
                checkpoint=self.sd_model_checkpoint,
                steps=self.steps,
                cfg=7,
                sampler=self.sampler_index,
                width=self.width,
                height=self.height,
                stop_event=self._stop_event,
                enable_hr=self.enable_hr,
                hr_scale=self.hr_scale,
                hr_upscaler=self.hr_upscaler,
                hr_second_pass_steps=self.hr_second_pass_steps,
                denoising_strength=self.denoising_strength,
                workflow_path=(COMFY_FLOWS_DIR / self.comfy_flow) if self.comfy_flow else None,
                model_overrides=self.comfy_model_overrides,
            )
        else:
            payload = {"prompt": prompt, "negative_prompt": negative, "steps": self.steps, "cfg_scale": 7, "enable_hr": self.enable_hr, "hr_scale": self.hr_scale, "hr_upscaler": self.hr_upscaler, "hr_second_pass_steps": self.hr_second_pass_steps, "denoising_strength": self.denoising_strength, "width": self.width, "height": self.height, "sampler_index": self.sampler_index, "override_settings": {"sd_model_checkpoint": self.sd_model_checkpoint}}
            if self.use_model_vae:
                payload["override_settings"]["sd_vae"] = "Automatic"
            response = requests.post(self.api_url, json=payload, timeout=self.api_timeout)
            response.raise_for_status()
            images = response.json().get("images", [])
            if images:
                image_bytes = base64.b64decode(images[0])
        if image_bytes:
            image_bytes = self._apply_nsfw_mosaic(image_bytes)
            image_bytes, output_extension = self._encoded_output(image_bytes)
            failure = None
            if self.enable_failure_isolation:
                failure = ImageFailureInspector(self.image_failure_min_variance).inspect(image_bytes)
            output_dir = Path(self.output_dir)
            if failure:
                output_dir = output_dir / "_image_failure"
            output = output_dir / f"image_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{output_extension}"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(image_bytes)
            prompt_path = self._save_prompt(output, prompt)
            if failure:
                report_path = self._save_failure_report(output, failure, prompt, negative)
                self._log(f"⚠️ 破綻候補を隔離しました: {output} / 記録: {report_path}")
            else:
                self._log(f"✅ 生成成功: {output}" + (f" / prompt: {prompt_path}" if prompt_path else ""))

    def _generate_sequential(self):
        source_path = self._select_source(self.input_file, self.root_dir)
        lines = self._read_lines(source_path) if source_path else []
        if not lines:
            self._log("⚠️ 順次生成するプロンプトがありません。")
            return

        total = len(lines)
        completed = 0
        self._log(f"▶️ 順次生成開始: {total}件" + "（無限ループ）" if self.sequential_loop else f"▶️ 順次生成開始: {total}件")
        while not self._stop_event.is_set():
            shared_wildcard_cache = {}
            for index, source_text in enumerate(lines, start=1):
                if self._stop_event.is_set(): break
                try:
                    prompt = self._expand_text(source_text, self.root_dir, wildcard_cache=shared_wildcard_cache)
                    self._log(f"📝 [{index}/{total}] {prompt}")
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
            if mode == "sequential":
                self._generate_sequential()
                return
            shared_wildcard_cache = {} if self.wildcard_cache_scope == "until_stop" else None
            while not self._stop_event.is_set():
                try:
                    self._generate(wildcard_cache=shared_wildcard_cache)
                except Exception as e:
                    self._log(f"❌ 生成エラー: {e}")
                if mode == "once":
                    break
        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _stop(self):
        self._stop_event.set()
