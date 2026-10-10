"""ComfyUI API adapter for generation model and option catalogs."""

from __future__ import annotations

from .comfyui_image_generation_backend import ComfyUIImageGenerationBackend
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
#   責務: [ComfyUIBackendCatalog: ComfyUI固有のAPIおよびローカル候補を共通形式で提供する]
#   フィールド: [_ENDPOINTS: API候補を取得するnode定義]
#   処理: [APIとComfyUI用モデル配置から候補を収集し, 共通形式で返す]
# }
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

    # {
    #   責務: [capabilities: ComfyUI adapterが提供する生成機能を返す]
    #   戻り値: [GenerationCapabilities: ComfyUIの対応機能]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return ComfyUIImageGenerationBackend.CAPABILITIES

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
    #   責務: [local_choices: ComfyUI用のローカル候補をルート設定から収集する]
    #   処理: [1: checkpoint, UNet, LoRA, VAEを共有先とruntime配置から走査する, 2: upscaler, sampler, workflow候補を追加する]
    #   引数: [self: catalog instance, roots: モデルとruntimeのルート, scan_model_files: モデルファイル走査関数, scan_flow_files: workflow走査関数, unique_choices: 候補の重複除去関数]
    #   戻り値: [ChoiceMap: ComfyUIで利用できるローカル候補]
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
        runtime_models = roots["runtime"] / "models"
        checkpoint_groups = [scan_model_files(roots["checkpoints"])]
        checkpoint_groups.extend(scan_model_files(path) for path in roots["legacy_checkpoints"])
        checkpoint_groups.append(scan_model_files(runtime_models / "checkpoints"))
        unet_roots = [
            models / "diffusion_models",
            models / "unet",
            legacy_models / "diffusion_models",
            legacy_models / "unet",
            runtime_models / "diffusion_models",
            runtime_models / "unet",
        ]
        lora_roots = [
            models / "Lora", models / "loras",
            legacy_models / "Lora", legacy_models / "loras",
            runtime_models / "loras",
        ]
        vae_roots = [
            models / "VAE", models / "vae",
            legacy_models / "VAE", legacy_models / "vae",
            runtime_models / "vae",
        ]
        return {
            "checkpoints": unique_choices([item for group in checkpoint_groups for item in group]),
            "unets": unique_choices([item for root in unet_roots for item in scan_model_files(root)]),
            "loras": unique_choices([item for root in lora_roots for item in scan_model_files(root)]),
            "vaes": unique_choices([item for root in vae_roots for item in scan_model_files(root)]),
            "upscalers": scan_model_files(runtime_models / "upscale_models"),
            "samplers": list(_COMFYUI_SAMPLER_CHOICES),
            "flows": unique_choices(
                scan_flow_files(roots["comfy_flows"])
                + scan_flow_files(legacy_models / "flows")
            ),
        }

    # {
    #   責務: [primary_model_choices: ComfyUIで選択できるcheckpointとUNet候補を返す]
    #   処理: [checkpointとUNet候補を結合し, 元の順序を保って重複除去する]
    #   引数: [self: catalog instance, choices: ComfyUI形式のモデル候補mapping]
    #   戻り値: [list[str]: 選択可能な主モデル名]
    # }
    def primary_model_choices(self, choices: ChoiceMap) -> list[str]:
        return list(dict.fromkeys([*choices.get("checkpoints", []), *choices.get("unets", [])]))


_COMFYUI_SAMPLER_CHOICES = [
    "euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral",
    "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "dpmpp_3m_sde",
    "ddim", "uni_pc",
]
