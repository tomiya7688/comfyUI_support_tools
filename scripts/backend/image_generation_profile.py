"""Backend-specific defaults for the Random Image generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .a1111_api_url import normalize_a1111_api_root
from .generation_backend_types import GenerationBackendId
from .generation_profile_inputs import GenerationProfileInputs


# {
#   責務: [ImageGenerationProfile: Random Imageのbackend別起動既定値を保持する]
#   フィールド: [backend: GenerationBackendId, api_url: 生成API URL, output_dir: 既定保存先, default_checkpoint: 既定checkpoint]
# }
@dataclass(frozen=True)
class ImageGenerationProfile:
    backend: GenerationBackendId
    api_url: str
    output_dir: Path
    default_checkpoint: str


# {
#   責務: [create_a1111_image_generation_profile: A1111向けRandom Image既定値を作る]
#   処理: [名前付き入力からA1111 API endpoint・保存先・既定checkpointをprofileへ設定する]
#   引数: [inputs: 共通profile設定値]
#   戻り値: [ImageGenerationProfile: A1111の生成既定値]
# }
def create_a1111_image_generation_profile(inputs: GenerationProfileInputs) -> ImageGenerationProfile:
    api_root = normalize_a1111_api_root(inputs.a1111_api_url)
    return ImageGenerationProfile(
        backend="a1111",
        api_url=f"{api_root}/sdapi/v1/txt2img",
        output_dir=inputs.a1111_directory / "outputs" / "txt2img-images" / inputs.date_folder,
        default_checkpoint="rinIllusionRNSFW_v30",
    )


# {
#   責務: [create_comfyui_image_generation_profile: ComfyUI向けRandom Image既定値を作る]
#   処理: [名前付き入力からComfyUI API・保存先・既定checkpointをprofileへ設定する]
#   引数: [inputs: 共通profile設定値]
#   戻り値: [ImageGenerationProfile: ComfyUIの生成既定値]
# }
def create_comfyui_image_generation_profile(inputs: GenerationProfileInputs) -> ImageGenerationProfile:
    return ImageGenerationProfile(
        backend="comfyui",
        api_url=inputs.comfyui_api_url.strip().rstrip("/"),
        output_dir=inputs.runtime_directory / "output" / "KadokaTools" / inputs.date_folder,
        default_checkpoint="shiitakeMix_v20.safetensors",
    )
