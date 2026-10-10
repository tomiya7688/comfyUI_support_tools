"""A1111 API adapter for generation model and option catalogs."""

from __future__ import annotations

from .a1111_image_generation_backend import A1111ImageGenerationBackend
from .generation_capabilities import GenerationCapabilities

from .generation_backend_catalog import (
    ChoiceMap,
    LocalRoots,
    RequestGet,
    ScanFlowFiles,
    ScanModelFiles,
    UniqueChoices,
)


# {
#   責務: [A1111BackendCatalog: A1111固有のAPIおよびローカル候補を共通形式で提供する]
#   フィールド: [_ENDPOINTS: API候補を取得するendpoint定義]
#   処理: [APIとA1111用モデル配置から候補を収集し, 共通形式で返す]
# }
class A1111BackendCatalog:
    """Query model, upscaler, and sampler names from the A1111 API."""

    _ENDPOINTS = (
        ("checkpoints", "sd-models", ("title", "model_name", "filename")),
        ("loras", "loras", ("name",)),
        ("vaes", "sd-vae", ("model_name", "filename", "name")),
        ("upscalers", "upscalers", ("name",)),
        ("samplers", "samplers", ("name",)),
    )

    # {
    #   責務: [capabilities: A1111 adapterが提供する生成機能を返す]
    #   戻り値: [GenerationCapabilities: A1111の対応機能]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return A1111ImageGenerationBackend.CAPABILITIES

    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        normalized_url = base_url.strip().rstrip("/")
        if "/sdapi/" in normalized_url:
            normalized_url = normalized_url.split("/sdapi/", 1)[0]
        choices: ChoiceMap = {"checkpoints": [], "unets": [], "loras": [], "vaes": [], "upscalers": [], "samplers": []}
        warnings = []
        for key, endpoint, fields in self._ENDPOINTS:
            try:
                response = request_get(f"{normalized_url}/sdapi/v1/{endpoint}", timeout=5)
                response.raise_for_status()
                for item in response.json():
                    if not isinstance(item, dict):
                        continue
                    value = next((item.get(field) for field in fields if item.get(field)), None)
                    if value:
                        choices[key].append(str(value))
            except Exception as error:
                warnings.append(f"{endpoint}: {error}")
        return choices, warnings

    # {
    #   責務: [local_choices: A1111用のローカル候補をルート設定から収集する]
    #   処理: [1: checkpoint, LoRA, VAEを共有先とA1111配置から走査する, 2: A1111用upscalerとsampler候補を加える]
    #   引数: [self: catalog instance, roots: モデルとruntimeのルート, scan_model_files: モデルファイル走査関数, scan_flow_files: 未使用の共通契約引数, unique_choices: 候補の重複除去関数]
    #   戻り値: [ChoiceMap: A1111で利用できるローカル候補]
    # }
    def local_choices(
        self,
        roots: LocalRoots,
        scan_model_files: ScanModelFiles,
        scan_flow_files: ScanFlowFiles,
        unique_choices: UniqueChoices,
    ) -> ChoiceMap:
        models = roots["models"]
        legacy_models = roots["legacy_models"]
        checkpoints = [scan_model_files(roots["checkpoints"])]
        checkpoints.extend(scan_model_files(path) for path in roots["legacy_checkpoints"])
        loras = [
            scan_model_files(models / "Lora"),
            scan_model_files(models / "loras"),
            scan_model_files(legacy_models / "Lora"),
            scan_model_files(legacy_models / "loras"),
            scan_model_files(roots["a1111"] / "models" / "Lora"),
        ]
        vaes = [
            scan_model_files(models / "VAE"),
            scan_model_files(models / "vae"),
            scan_model_files(legacy_models / "VAE"),
            scan_model_files(legacy_models / "vae"),
            scan_model_files(roots["a1111"] / "models" / "VAE"),
            scan_model_files(roots["runtime"] / "models" / "VAE"),
        ]
        upscalers = list(_A1111_UPSCALER_CHOICES)
        model_root = roots["runtime"] / "models"
        for folder_name in ("ESRGAN", "RealESRGAN", "SwinIR", "LDSR", "ScuNET", "BSRGAN"):
            upscalers.extend(scan_model_files(model_root / folder_name, keep_suffix=False))
        return {
            "checkpoints": unique_choices([item for group in checkpoints for item in group]),
            "unets": [],
            "loras": unique_choices([item for group in loras for item in group]),
            "vaes": unique_choices([item for group in vaes for item in group]),
            "upscalers": unique_choices(upscalers),
            "samplers": list(_A1111_SAMPLER_CHOICES),
            "flows": [],
        }

    # {
    #   責務: [primary_model_choices: A1111で選択できるcheckpoint候補を返す]
    #   処理: [checkpoint候補を順序を保って重複除去し, unet候補は主モデルに含めない]
    #   引数: [self: catalog instance, choices: A1111形式のモデル候補mapping]
    #   戻り値: [list[str]: 選択可能なcheckpoint名]
    # }
    def primary_model_choices(self, choices: ChoiceMap) -> list[str]:
        return list(dict.fromkeys(choices.get("checkpoints", [])))


_A1111_SAMPLER_CHOICES = [
    "Euler a", "Euler", "DPM++ 2M", "DPM++ 2M Karras",
    "DPM++ SDE", "DPM++ SDE Karras", "DDIM", "UniPC",
]
_A1111_UPSCALER_CHOICES = [
    "None", "Lanczos", "Nearest", "Latent", "Latent (antialiased)",
    "R-ESRGAN 4x+", "R-ESRGAN 4x+ Anime6B",
]
