import io
import json

from PIL import Image

from ..context import *
from .image_generation_backend_factory import create_image_generation_backend
from .text_to_image_request import TextToImageRequest
from .image_failure_inspector import ImageFailureInspector
from .ollama_prompt_corrector import OllamaPromptCorrector
from .generation_parameter_resolver import GenerationParameterResolver
from .prompt_lora_compatibility import validate_prompt_loras

# {
# 責務: [EmbeddedRandomImage: wildcard promptを解決し生成backendで画像を順次または反復生成する]
# フィールド: [input_file: 正prompt source, negative_input_file: 負prompt source,
# root_dir: wildcard探索root, output_dir: 生成画像保存先,
# wildcard_cache_scope: wildcard結果の再利用範囲, sequential_reuse_wildcards: 順次処理内cache設定,
# _active_backend: 現在の生成backend, _stop_event: worker停止通知,
# _worker_thread: 実行worker, _pending_settings: 次画像から適用する設定]
# 処理: [1: wildcardと追加promptを展開する, 2: backendへ生成要求を渡す,
# 3: 画像・metadata・prompt・failure reportを保存する]
# }
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
    ollama_api_url = "http://127.0.0.1:11434"
    ollama_model = ""

    # {
    # 責務: [__init__: 既定設定をinstance用に複製しworker制御状態を初期化する]
    # 処理: [1: mutable設定をcopyする, 2: stop event・backend参照・worker thread・lockを用意する,
    # 3: pending設定とlog callbackを設定する]
    # 引数: []
    # 戻り値: []
    # }
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
    # 責務: [queue_settings_update: 実行中workerが次の画像前に適用する設定を予約する]
    # 処理: [1: lock内でsettingsをcopyしてpending領域へ置く]
    # 引数: [settings: 次の生成へ反映する設定mapping]
    # 戻り値: []
    # }
    def queue_settings_update(self, settings):
        """Stage settings so a running worker applies them before its next image."""
        with self._settings_lock:
            self._pending_settings = dict(settings)

    # {
    # 責務: [_apply_pending_settings: 予約済み設定をatomicに取り出してinstanceへ反映する]
    # 処理: [1: lock内でpending値を取得・clearする, 2: 各fieldへ設定し適用logを出す]
    # 引数: []
    # 戻り値: [設定を適用した場合はTrue、pendingがなければFalse]
    # }
    def _apply_pending_settings(self):
        with self._settings_lock:
            settings = self._pending_settings
            self._pending_settings = None
        if settings is None:
            return False
        for key, value in settings.items():
            setattr(self, key, value)
        self._log("🔄 次の生成へ設定更新を適用しました")
        return True

    # {
    # 責務: [_select_source: file参照またはwildcard directoryからsource fileを解決する]
    # 処理: [1: root相対pathを組み立てる, 2: 拡張子なし同名directoryを許容する,
    # 3: directoryなら配下txtから1件を選びlogする]
    # 引数: [rel_path: source fileまたはdirectory指定, root: 任意のwildcard root]
    # 戻り値: [選択されたPath、候補がなければNone]
    # }
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

    # {
    # 責務: [_read_lines: UTF-8 text fileから空行を除いた行を取得する]
    # 処理: [1: fileを読み各行をtrimする, 2: file不存在をlogして空一覧を返す]
    # 引数: [path: 読み込むtext file path]
    # 戻り値: [空でない行の一覧]
    # }
    def _read_lines(self, path):
        try:
            with open(path, encoding="utf-8") as source:
                return [line.strip() for line in source if line.strip()]
        except FileNotFoundError:
            self._log(f"⚠️ ファイルが見つかりません: {path}")
            return []

    # {
    # 責務: [_expand_text: inline choice・LoRA保護・nested wildcardをprompt内で展開する]
    # 処理: [1: brace choiceから候補を選ぶ, 2: LoRA表記を一時保護する,
    # 3: wildcard tokenを再帰展開してLoRA表記を戻す]
    # 引数: [text: 展開するprompt断片, root: wildcard探索root, depth: nested展開深度,
    # wildcard_cache: 任意の解決結果cache]
    # 戻り値: [展開後text]
    # }
    def _expand_text(self, text, root, depth=0, wildcard_cache=None):
        pattern = re.compile(r"\{([^{}]+)\}")
        while pattern.search(text):
            match = pattern.search(text)
            text = text[:match.start()] + secrets.choice(match.group(1).split("|")) + text[match.end():]
        placeholders = {}
        text = re.sub(r"<[^>]*>", lambda match: placeholders.setdefault(f"__LORA_{len(placeholders)}__", match.group(0)), text)

        # {
        # 責務: [expand_wildcard: wildcard tokenをfile参照へ変換し再帰展開する]
        # 処理: [1: LoRA保護tokenをそのまま維持する, 2: token名に対応するtxtをprocess_fileへ渡す]
        # 引数: [match: 正規表現が検出したwildcard token]
        # 戻り値: [wildcard展開後textまたは保護token]
        # }
        def expand_wildcard(match):
            name = match.group(1)
            if name.startswith("LORA_"):
                return match.group(0)
            return self.process_file(name.strip("_") + ".txt", root, depth + 1, wildcard_cache)

        text = re.sub(r"__(.*?)__", expand_wildcard, text)
        for key, value in placeholders.items():
            text = text.replace(key, value)
        return text

    # {
    # 責務: [process_file: wildcard fileから1行を選びnested tokenを再帰展開する]
    # 処理: [1: depth上限とcacheを確認する, 2: file・directoryを解決して行を選ぶ,
    # 3: nested textを展開してcacheへ保存する]
    # 引数: [rel_path: wildcard text指定, root: 任意の探索root, depth: 再帰深度,
    # wildcard_cache: 同一結果を再利用する任意cache]
    # 戻り値: [展開済みwildcard text、解決不能・空時は空文字]
    # }
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

    # {
    # 責務: [_additional_entries: 新旧設定形式の追加prompt指定を共通entryへそろえる]
    # 処理: [1: structured entryがあればpath有効なものに絞る, 2: なければlegacy file一覧をentry化する]
    # 引数: []
    # 戻り値: [path・position・cache scopeを持つ追加prompt entry一覧]
    # }
    def _additional_entries(self):
        if self.additional_inputs:
            return [item for item in self.additional_inputs if item.get("path")]
        return [
            {"path": path, "label": "", "position": self.additional_position, "cache_scope": self.wildcard_cache_scope}
            for path in self.additional_input_files if path
        ]

    # {
    # 責務: [_additional_prompts: 追加wildcard fileを展開しprefix・suffixへ分ける]
    # 処理: [1: entryごとにcache scopeを選ぶ, 2: wildcard textを展開する,
    # 3: positionに応じてprefixとsuffixへ振り分ける]
    # 引数: [wildcard_cache: 呼び出し元が共有する任意cache]
    # 戻り値: [prefix listとsuffix listの組]
    # }
    def _additional_prompts(self, wildcard_cache=None):
        prefix, suffix = [], []
        for item in self._additional_entries():
            cache = wildcard_cache if item.get("cache_scope") == "until_stop" else None
            part = self.process_file(item["path"], self.root_dir, wildcard_cache=cache)
            if not part:
                continue
            (suffix if item.get("position") == "suffix" else prefix).append(part)
        return prefix, suffix

    # {
    # 責務: [_with_additional_prompt: prefix追加prompt・元prompt・suffixを連結する]
    # 処理: [1: 追加promptを解決する, 2: 空要素を避けて順序どおり連結する]
    # 引数: [prompt: 元の生成prompt, wildcard_cache: 共有可能なwildcard cache]
    # 戻り値: [追加promptを含むcomma区切りprompt]
    # }
    def _with_additional_prompt(self, prompt, wildcard_cache=None):
        prefix, suffix = self._additional_prompts(wildcard_cache)
        parts = [*prefix]
        if prompt:
            parts.append(prompt)
        parts.extend(suffix)
        return ", ".join(parts)

    # {
    # 責務: [_action_condition_matches: 条件式を展開済みprompt tagへ照合する]
    # 処理: [1: vertical barでOR候補へ分ける, 2: 各候補内comma tagをAND照合する]
    # 引数: [condition: comma-AND・pipe-OR条件式, normalized_prompt: 正規化済みprompt]
    # 戻り値: [いずれかの条件候補が一致した場合はTrue]
    # }
    @staticmethod
    def _action_condition_matches(condition, normalized_prompt):
        """`,` はAND、`|` はORとして展開済みプロンプトのタグを照合する。"""
        alternatives = [item.strip() for item in condition.split("|") if item.strip()]
        return any(all(tag.strip() in normalized_prompt for tag in item.split(",") if tag.strip()) for item in alternatives)

    # {
    # 責務: [_with_action_prompt: prompt条件に一致したaction wildcardを追加する]
    # 処理: [1: promptとcondition表記を正規化する, 2: 一致entryだけ展開する,
    # 3: position別に追加して一致内容をlogする]
    # 引数: [prompt: wildcard展開済みprompt, wildcard_cache: 任意の共有cache]
    # 戻り値: [action wildcardを含むprompt]
    # }
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
    # 責務: [_apply_nsfw_mosaic: 対応環境でNudeNet検出領域にpixelate処理を要求する]
    # 処理: [1: optionとbackendを確認する, 2: censor APIへ画像と設定を送る,
    # 3: censored bytesまたは元画像を返す]
    # 引数: [image_bytes: encode済み生成画像]
    # 戻り値: [モザイク処理後または元の画像bytes]
    # }
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

    # {
    # 責務: [_save_failure_report: 破綻候補画像の生成条件をuser dataへJSON保存する]
    # 処理: [1: failure log directoryを作る, 2: path・backend・model・prompt等を記録する,
    # 3: output stem名のJSONを保存する]
    # 引数: [output: 破綻候補画像path, failure: 検出理由, prompt: 正prompt,
    # negative: 負prompt, parameters: 確定生成parameter]
    # 戻り値: [保存したreport path]
    # }
    def _save_failure_report(self, output, failure, prompt, negative, parameters):
        report_dir = USER_DATA_DIR / "output" / "image_generate" / "log" / "image_failure"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "output": str(output), "failure": failure, "backend": RUNTIME_BACKEND,
            "checkpoint": self.sd_model_checkpoint, "sampler": self.sampler_index,
            "width": self.width, "height": self.height, "steps": self.steps,
            "generation_parameters": parameters,
            "prompt": prompt, "negative_prompt": negative,
        }
        report_path = report_dir / f"{output.stem}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report_path

    # {
    # 責務: [_resolve_generation_parameters: UI設定または既定値から確定生成parameterを得る]
    # 処理: [1: 明示configurationの有無を確認する, 2: 未指定なら現在設定をfixed値にする,
    # 3: resolverで型・範囲を検証する]
    # 引数: []
    # 戻り値: [cfg・steps・resolution・samplerの確定値]
    # }
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

    # {
    # 責務: [_save_generation_metadata: 生成画像と同名のbackend・model・parameter JSONを保存する]
    # 処理: [1: sidecar pathを作る, 2: backend・checkpoint・確定parameterを記録する,
    # 3: UTF-8 JSONを書き込む]
    # 引数: [image_path: 保存済み画像path, parameters: 生成時parameter]
    # 戻り値: [生成metadata sidecar path]
    # }
    def _save_generation_metadata(self, image_path, parameters):
        metadata_path = image_path.with_suffix(".generation.json")
        metadata = {
            "backend": RUNTIME_BACKEND,
            "checkpoint": self.sd_model_checkpoint,
            **parameters,
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return metadata_path

    # {
    # 責務: [_save_prompt: optionに応じpromptを共通fileまたは画像別sidecarへ保存する]
    # 処理: [1: 保存設定を確認する, 2: file指定なら追記しdirectory指定ならstem別textを作る]
    # 引数: [image_output: 対応画像path, prompt: 保存する展開済みprompt]
    # 戻り値: [保存path、保存無効ならNone]
    # }
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

    # {
    # 責務: [_encoded_output: 生成画像を選択形式に変換し拡張子を決める]
    # 処理: [1: PNGと非対応formatを無変換扱いにする, 2: WebP・JPEG・GIFへencodeする]
    # 引数: [image_bytes: backendから得た画像bytes]
    # 戻り値: [保存bytesとfile extensionの組]
    # }
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

    # {
    # 責務: [_correct_prompt: option有効時だけOllamaへ展開済みpromptの補正を依頼する]
    # 処理: [1: 無効なら入力を返す, 2: OllamaCorrectorを呼んで結果をlogする]
    # 引数: [prompt: 追加wildcard適用後のprompt]
    # 戻り値: [補正promptまたは元prompt]
    # }
    def _correct_prompt(self, prompt):
        """Correct the fully expanded prompt only when the user enabled Ollama."""
        if not self.enable_prompt_correction:
            return prompt
        corrected = OllamaPromptCorrector().correct(self.ollama_api_url, self.ollama_model, prompt, requests)
        self._log(f"🪄 Ollamaでプロンプトを補正しました: {corrected}")
        return corrected

    # {
    # 責務: [_generate: promptを準備しbackendで画像を生成して成果物とmetadataを保存する]
    # 処理: [1: prompt・LoRA・generation parameterを解決する, 2: backend capabilityを検証して生成する,
    # 3: mosaic・format・failure isolationを適用し画像とsidecarを保存する]
    # 引数: [prompt: 任意の事前展開済み正prompt, negative: 任意の負prompt,
    # wildcard_cache: 呼び出し単位の共有wildcard cache]
    # 戻り値: []
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
        workflow_has_model_overrides = (
            RUNTIME_BACKEND == "comfyui" and bool(self.comfy_model_overrides)
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
        resolution = parameters["resolution"]
        self._log(
            "🎛️ 生成パラメータ: "
            f"CFG={parameters['cfg']:g}, Steps={parameters['steps']}, "
            f"Resolution={resolution['width']}x{resolution['height']}, "
            f"Sampler={parameters['sampler']}"
        )
        workflow_path = resolve_comfy_flow_path(self.comfy_flow) if self.comfy_flow else None
        backend = create_image_generation_backend(
            RUNTIME_BACKEND,
            self.api_url,
            self.api_timeout,
            request_post=requests.post,
        )
        if workflow_path and not backend.capabilities.supports("workflow"):
            raise ValueError("選択中の生成バックエンドはカスタムworkflowに対応していません")
        if self.enable_hr and not backend.capabilities.supports("hires_fix"):
            raise ValueError("選択中の生成バックエンドはHires Fixに対応していません")
        self._active_backend = backend
        try:
            image_bytes = backend.generate(
                TextToImageRequest(
                prompt=prompt,
                negative=negative,
                checkpoint=self.sd_model_checkpoint,
                steps=parameters["steps"],
                cfg=parameters["cfg"],
                sampler=parameters["sampler"],
                width=resolution["width"],
                height=resolution["height"],
                use_model_vae=self.use_model_vae,
                vae_name=self.vae_name,
                enable_hr=self.enable_hr,
                hr_scale=self.hr_scale,
                hr_upscaler=self.hr_upscaler,
                hr_second_pass_steps=self.hr_second_pass_steps,
                denoising_strength=self.denoising_strength,
                workflow_path=workflow_path,
                model_overrides=self.comfy_model_overrides,
                ),
                stop_event=self._stop_event,
            )
        finally:
            if self._active_backend is backend:
                self._active_backend = None
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
            metadata_path = self._save_generation_metadata(output, parameters)
            prompt_path = self._save_prompt(output, prompt)
            if failure:
                report_path = self._save_failure_report(output, failure, prompt, negative, parameters)
                self._log(f"⚠️ 破綻候補を隔離しました: {output} / 記録: {report_path}")
            else:
                self._log(
                    f"✅ 生成成功: {output} / parameters: {metadata_path}"
                    + (f" / prompt: {prompt_path}" if prompt_path else "")
                )

    # {
    # 責務: [_sequential_prompt_sources: 順次生成対象を単一text fileまたはdirectoryから列挙する]
    # 処理: [1: input pathをroot基準で解決する, 2: 拡張子なしdirectoryを許容する,
    # 3: directoryなら配下text fileをcasefold順で返す]
    # 引数: []
    # 戻り値: [順次読むprompt source path一覧]
    # }
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

    # {
    # 責務: [_generate_sequential: source fileの全非空行を一件ずつ生成へ渡す]
    # 処理: [1: fileとprompt行を列挙する, 2: 必要なら1巡共有wildcard cacheを作る,
    # 3: 各行を展開・生成し失敗を個別logする, 4: loop設定に応じて繰り返す]
    # 引数: []
    # 戻り値: []
    # }
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

    # {
    # 責務: [_start_thread: modeに応じた生成workerを重複防止付きで開始する]
    # 処理: [1: worker稼働中なら拒否する, 2: stop eventをclearする,
    # 3: mode別workerをdaemon threadとして起動する]
    # 引数: [mode: sequential・once・連続生成の実行mode]
    # 戻り値: []
    # }
    def _start_thread(self, mode):
        if self._worker_thread and self._worker_thread.is_alive():
            self._log("実行中: すでに生成中です。停止してから開始してください。")
            return
        self._stop_event.clear()
        # {
        # 責務: [worker: 選択modeに応じて設定適用と画像生成を停止まで実行する]
        # 処理: [1: sequentialなら順次生成を実行する, 2: それ以外はwildcard cacheを準備し,
        # 3: pending設定を適用しgenerateする, 4: once modeなら一回で終える]
        # 引数: []
        # 戻り値: []
        # }
        def worker():
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

    # {
    # 責務: [_stop: worker停止を通知し対応backendへ非同期interruptを要求する]
    # 処理: [1: stop eventをsetする, 2: active backend capabilityを確認する,
    # 3: 対応する場合にinterrupt helper threadを開始する]
    # 引数: []
    # 戻り値: []
    # }
    def _stop(self):
        self._stop_event.set()
        backend = self._active_backend
        if backend is None or not backend.capabilities.supports("interrupt"):
            return
        threading.Thread(target=self._interrupt_backend, args=(backend,), daemon=True).start()

    # {
    # 責務: [_interrupt_backend: backend interruptを呼び出し成否をlogする]
    # 処理: [1: interrupt APIを呼ぶ, 2: 成功または例外をlogする]
    # 引数: [backend: interrupt対応を表明した生成backend]
    # 戻り値: []
    # }
    def _interrupt_backend(self, backend):
        try:
            backend.interrupt()
            self._log("⏹️ 生成中断をバックエンドへ送信しました")
        except Exception as error:
            self._log(f"⚠️ バックエンド中断に失敗しました: {error}")
