"""ComfyUI API adapter for generation model and option catalogs."""

from __future__ import annotations

from .generation_backend_catalog import ChoiceMap, RequestGet


class ComfyUIBackendCatalog:
    """Query registered loader and sampler names from ComfyUI object info."""

    _ENDPOINTS = (
        ("checkpoints", "CheckpointLoaderSimple", "ckpt_name"),
        ("upscalers", "UpscaleModelLoader", "model_name"),
        ("samplers", "KSampler", "sampler_name"),
    )

    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        normalized_url = base_url.strip().rstrip("/")
        choices: ChoiceMap = {"checkpoints": [], "upscalers": [], "samplers": []}
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
