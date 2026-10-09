"""ComfyUI API adapter for generation model and option catalogs."""

from __future__ import annotations

from .generation_backend_catalog import ChoiceMap, RequestGet


class ComfyUIBackendCatalog:
    """Query registered loader and sampler names from ComfyUI object info."""

    _ENDPOINTS = (
        ("checkpoints", "CheckpointLoaderSimple", "ckpt_name"),
        ("unets", "UNETLoader", "unet_name"),
        ("loras", "LoraLoader", "lora_name"),
        ("vaes", "VAELoader", "vae_name"),
        ("upscalers", "UpscaleModelLoader", "model_name"),
        ("samplers", "KSampler", "sampler_name"),
    )

    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        normalized_url = base_url.strip().rstrip("/")
        choices: ChoiceMap = {"checkpoints": [], "unets": [], "loras": [], "vaes": [], "upscalers": [], "samplers": []}
        warnings = []
        for key, node_name, input_name in self._ENDPOINTS:
            try:
                response = request_get(f"{normalized_url}/object_info/{node_name}", timeout=5)
                response.raise_for_status()
                payload = response.json()
                node_info = payload.get(node_name, payload) if isinstance(payload, dict) else {}
                spec = node_info.get("input", {}).get("required", {}).get(input_name, [])
                if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
                    choices[key].extend(str(value) for value in spec[0])
            except Exception as error:
                warnings.append(f"{node_name}: {error}")
        return choices, warnings

    # {
    #   責務: [primary_model_choices: ComfyUIで選択できるcheckpointとUNet候補を返す]
    #   処理: [checkpointとUNet候補を結合し, 元の順序を保って重複除去する]
    #   引数: [self: catalog instance, choices: ComfyUI形式のモデル候補mapping]
    #   戻り値: [list[str]: 選択可能な主モデル名]
    # }
    def primary_model_choices(self, choices: ChoiceMap) -> list[str]:
        return list(dict.fromkeys([*choices.get("checkpoints", []), *choices.get("unets", [])]))
