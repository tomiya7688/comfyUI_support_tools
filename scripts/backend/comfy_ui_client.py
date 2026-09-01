from ..context import *
import copy

class ComfyUIClient:
    DEFAULT_WORKFLOW_PATH = COMFY_FLOWS_DIR / "default.json"
    SAMPLER_MAP = {
        "Euler": "euler",
        "Euler a": "euler_ancestral",
        "DPM++ 2M": "dpmpp_2m",
        "DPM++ 2M Karras": "dpmpp_2m",
        "DPM++ SDE": "dpmpp_sde",
        "DPM++ SDE Karras": "dpmpp_sde",
    }

    def __init__(self, base_url="http://127.0.0.1:8188", timeout=10000):
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def sampler_name(cls, value):
        return cls.SAMPLER_MAP.get(value, value.strip().lower().replace(" ", "_"))

    @staticmethod
    def scheduler_name(value):
        return "karras" if "Karras" in value else "normal"

    def _queue_and_fetch(self, workflow, stop_event=None):
        response = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
            timeout=min(self.timeout, 60),
        )
        response.raise_for_status()
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUIからprompt_idが返りません: {response.text[:200]}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return None
            history_response = requests.get(
                f"{self.base_url}/history/{prompt_id}",
                timeout=30,
            )
            history_response.raise_for_status()
            history = history_response.json().get(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI生成エラー: {messages}")
                for output in history.get("outputs", {}).values():
                    for image_info in output.get("images", []):
                        image_response = requests.get(
                            f"{self.base_url}/view",
                            params={
                                "filename": image_info["filename"],
                                "subfolder": image_info.get("subfolder", ""),
                                "type": image_info.get("type", "output"),
                            },
                            timeout=60,
                        )
                        image_response.raise_for_status()
                        return image_response.content
                raise RuntimeError("ComfyUIの履歴に出力画像がありません")
            time.sleep(0.5)
        raise TimeoutError(f"ComfyUI生成が{self.timeout}秒以内に完了しませんでした")

    def _workflow(
        self,
        prompt,
        negative,
        checkpoint,
        steps,
        cfg,
        sampler,
        width,
        height,
        denoise=1.0,
        latent_node=None,
    ):
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": cfg,
                    "denoise": denoise,
                    "latent_image": ["5", 0] if latent_node is None else latent_node,
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": self.sampler_name(sampler),
                    "scheduler": self.scheduler_name(sampler),
                    "seed": secrets.randbelow(2**63),
                    "steps": steps,
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": prompt},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": negative},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "PreviewImage",
                "inputs": {"images": ["8", 0]},
            },
        }
        if latent_node is None:
            workflow["5"] = {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": height, "width": width},
            }
        return workflow

    @staticmethod
    def _load_workflow(path):
        with Path(path).open(encoding="utf-8") as source:
            workflow = json.load(source)
        if not isinstance(workflow, dict):
            raise ValueError("ComfyUIフローはAPI形式のJSONオブジェクトで指定してください")
        if isinstance(workflow.get("nodes"), list):
            workflow = ComfyUIClient._expand_single_subgraph(workflow)
            return ComfyUIClient._editor_workflow_to_api(workflow)
        return copy.deepcopy(workflow)

    @staticmethod
    def _expand_single_subgraph(workflow):
        definitions = workflow.get("definitions", {})
        subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
        nodes = workflow.get("nodes", [])
        if len(nodes) != 1 or not isinstance(subgraphs, list): return workflow
        subgraph = next((item for item in subgraphs if item.get("id") == nodes[0].get("type")), None)
        if not isinstance(subgraph, dict) or not isinstance(subgraph.get("nodes"), list): return workflow
        expanded, links = copy.deepcopy(subgraph["nodes"]), []
        for link in subgraph.get("links", []):
            if isinstance(link, dict) and link.get("origin_id", 0) >= 0: links.append([link["id"], link["origin_id"], link["origin_slot"], link["target_id"], link["target_slot"], link.get("type", "*")])
        for node in expanded:
            values = node.get("widgets_values", [])
            if node.get("type") == "CLIPLoader" and values and values[0] == "qwen_3_06b_base.safetensors": values[1] = "qwen_image"
            if node.get("type") == "UNETLoader" and values and values[0] == "anima-base-v1.0.safetensors": values[0] = "anima_baseV10.safetensors"
            if node.get("type") == "KSampler" and len(values) >= 7:
                node["widgets_values"] = [values[0], values[2], values[3], values[4], values[5], values[6]]
        expanded.append({"id":999,"type":"SaveImage","inputs":[{"name":"images","link":82},{"name":"filename_prefix","widget":{"name":"filename_prefix"}}],"widgets_values":["KadokaTools/Anima"]})
        links.append([1000,8,0,999,0,"IMAGE"])
        return {"nodes":expanded,"links":links}

    @staticmethod
    def _editor_workflow_to_api(workflow):
        links = {link[0]: link for link in workflow.get("links", []) if isinstance(link, list) and len(link) >= 5}
        converted = {}
        for node in workflow["nodes"]:
            node_id = str(node["id"])
            inputs = {}
            widget_values = iter(node.get("widgets_values", []))
            for item in node.get("inputs", []):
                name = item.get("name")
                if not name:
                    continue
                if item.get("link") is not None and item["link"] in links:
                    link = links[item["link"]]
                    inputs[name] = [str(link[1]), link[2]]
                elif "widget" in item:
                    try:
                        inputs[name] = next(widget_values)
                    except StopIteration:
                        pass
            converted[node_id] = {"class_type": node["type"], "inputs": inputs, "_meta": {"title": node.get("title", "")}}
        return converted

    @classmethod
    def model_inputs(cls, workflow_path):
        """フローにあるモデル選択入力を、ノードIDつきで返す。"""
        workflow = cls._load_workflow(workflow_path)
        result = []
        pattern = re.compile(r"(?:ckpt|unet|vae|clip|model)_name(?:_\d+)?$", re.IGNORECASE)
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            title = str(node.get("_meta", {}).get("title") or node.get("class_type") or node_id)
            for name, value in inputs.items():
                if pattern.fullmatch(name):
                    result.append({"id": f"{node_id}:{name}", "label": f"{title} / {name}", "value": str(value)})
        return result

    @staticmethod
    def _apply_parameters(workflow, prompt, negative, checkpoint, steps, cfg, sampler, width, height, model_overrides=None):
        model_overrides = model_overrides or {}
        clip_nodes = [node for node in workflow.values() if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"]
        clip_index = 0
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            kind = node.get("class_type")
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for name in tuple(inputs):
                field_id = f"{node_id}:{name}"
                if field_id in model_overrides and model_overrides[field_id]:
                    inputs[name] = model_overrides[field_id]
            if kind == "CheckpointLoaderSimple" and "ckpt_name" in inputs and f"{node_id}:ckpt_name" not in model_overrides: inputs["ckpt_name"] = checkpoint
            elif kind == "UNETLoader" and "unet_name" in inputs and f"{node_id}:unet_name" not in model_overrides and not str(inputs["unet_name"]).startswith("anima_"):
                inputs["unet_name"] = checkpoint
            elif kind == "CLIPTextEncode" and "text" in inputs:
                marker = str(node.get("_meta", {})).lower()
                inputs["text"] = negative if "negative" in marker else (prompt if clip_index == 0 else negative)
                clip_index += 1
            elif kind == "KSampler":
                inputs.update({"steps": steps, "cfg": cfg, "sampler_name": ComfyUIClient.sampler_name(sampler), "seed": secrets.randbelow(2**63)})
            elif kind == "EmptyLatentImage":
                inputs.update({"width": width, "height": height, "batch_size": 1})

    def txt2img(
        self,
        prompt,
        negative,
        checkpoint,
        steps,
        cfg,
        sampler,
        width,
        height,
        stop_event=None,
        *,
        enable_hr=False,
        hr_scale=1.5,
        hr_upscaler="",
        hr_second_pass_steps=20,
        denoising_strength=0.7,
        workflow_path=None,
        model_overrides=None,
    ):
        workflow_path = workflow_path or (self.DEFAULT_WORKFLOW_PATH if self.DEFAULT_WORKFLOW_PATH.is_file() else None)
        workflow = self._load_workflow(workflow_path) if workflow_path else self._workflow(
            prompt,
            negative,
            checkpoint,
            steps,
            cfg,
            sampler,
            width,
            height,
        )
        if workflow_path:
            self._apply_parameters(workflow, prompt, negative, checkpoint, steps, cfg, sampler, width, height, model_overrides)
        if enable_hr:
            if not hr_upscaler or hr_upscaler == "None":
                raise ValueError("ComfyUIでhires fixを使う場合はupscalerモデルを選択してください")
            target_width = max(8, int(width * hr_scale) // 8 * 8)
            target_height = max(8, int(height * hr_scale) // 8 * 8)
            workflow.update({
                "13": {
                    "class_type": "UpscaleModelLoader",
                    "inputs": {"model_name": hr_upscaler},
                },
                "14": {
                    "class_type": "ImageUpscaleWithModel",
                    "inputs": {"image": ["8", 0], "upscale_model": ["13", 0]},
                },
                "15": {
                    "class_type": "ImageScale",
                    "inputs": {
                        "crop": "disabled",
                        "height": target_height,
                        "image": ["14", 0],
                        "upscale_method": "lanczos",
                        "width": target_width,
                    },
                },
                "16": {
                    "class_type": "VAEEncode",
                    "inputs": {"pixels": ["15", 0], "vae": ["4", 2]},
                },
                "17": {
                    "class_type": "KSampler",
                    "inputs": {
                        "cfg": cfg,
                        "denoise": denoising_strength,
                        "latent_image": ["16", 0],
                        "model": ["4", 0],
                        "negative": ["7", 0],
                        "positive": ["6", 0],
                        "sampler_name": self.sampler_name(sampler),
                        "scheduler": self.scheduler_name(sampler),
                        "seed": secrets.randbelow(2**63),
                        "steps": max(1, int(hr_second_pass_steps)),
                    },
                },
                "18": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["17", 0], "vae": ["4", 2]},
                },
            })
            workflow["9"]["inputs"]["images"] = ["18", 0]
        return self._queue_and_fetch(workflow, stop_event)

    def img2img(
        self,
        image_path,
        prompt,
        negative,
        checkpoint,
        steps,
        cfg,
        sampler,
        denoise,
        width,
        height,
        stop_event=None,
    ):
        upload_name = f"kadoka_{secrets.token_hex(8)}{image_path.suffix.lower()}"
        with image_path.open("rb") as source:
            upload_response = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (upload_name, source, "application/octet-stream")},
                data={"overwrite": "true", "type": "input"},
                timeout=120,
            )
        upload_response.raise_for_status()
        uploaded = upload_response.json()
        uploaded_name = uploaded.get("name", upload_name)
        if uploaded.get("subfolder"):
            uploaded_name = f"{uploaded['subfolder']}/{uploaded_name}"

        workflow = self._workflow(
            prompt,
            negative,
            checkpoint,
            steps,
            cfg,
            sampler,
            0,
            0,
            denoise=denoise,
            latent_node=["11", 0],
        )
        workflow["10"] = {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        }
        workflow["12"] = {
            "class_type": "ImageScale",
            "inputs": {
                "crop": "disabled",
                "height": height,
                "image": ["10", 0],
                "upscale_method": "lanczos",
                "width": width,
            },
        }
        workflow["11"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["12", 0], "vae": ["4", 2]},
        }
        return self._queue_and_fetch(workflow, stop_event)
