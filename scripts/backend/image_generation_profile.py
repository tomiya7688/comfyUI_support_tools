"""Backend-specific defaults for the Random Image generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .a1111_api_url import normalize_a1111_api_root


# {
#   責務: [ImageGenerationProfile: Random Imageのbackend別起動既定値を保持する]
#   フィールド: [backend: backend識別子, api_url: 生成API URL, output_dir: 既定保存先, default_checkpoint: 既定checkpoint]
# }
@dataclass(frozen=True)
class ImageGenerationProfile:
    backend: str
    api_url: str
    output_dir: Path
    default_checkpoint: str


# {
#   責務: [create_a1111_image_generation_profile: A1111向けRandom Image既定値を作る]
#   処理: [A1111 API endpoint・保存先・既定checkpointをprofileへ設定する]
#   引数: [a1111_api_url: A1111 API URL, comfyui_api_url: 未使用の共通互換引数, a1111_dir: A1111 runtime root, runtime_dir: 未使用の共通互換引数, date_folder: 日付別保存フォルダー名]
#   戻り値: [ImageGenerationProfile: A1111の生成既定値]
# }
def create_a1111_image_generation_profile(
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    date_folder: str,
) -> ImageGenerationProfile:
    del comfyui_api_url, runtime_dir
    api_root = normalize_a1111_api_root(a1111_api_url)
    return ImageGenerationProfile(
        backend="a1111",
        api_url=f"{api_root}/sdapi/v1/txt2img",
        output_dir=a1111_dir / "outputs" / "txt2img-images" / date_folder,
        default_checkpoint="rinIllusionRNSFW_v30",
    )


# {
#   責務: [create_comfyui_image_generation_profile: ComfyUI向けRandom Image既定値を作る]
#   処理: [ComfyUI API・保存先・既定checkpointをprofileへ設定する]
#   引数: [a1111_api_url: 未使用の共通互換引数, comfyui_api_url: ComfyUI API URL, a1111_dir: 未使用の共通互換引数, runtime_dir: ComfyUI runtime root, date_folder: 日付別保存フォルダー名]
#   戻り値: [ImageGenerationProfile: ComfyUIの生成既定値]
# }
def create_comfyui_image_generation_profile(
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    date_folder: str,
) -> ImageGenerationProfile:
    del a1111_api_url, a1111_dir
    return ImageGenerationProfile(
        backend="comfyui",
        api_url=comfyui_api_url.strip().rstrip("/"),
        output_dir=runtime_dir / "output" / "KadokaTools" / date_folder,
        default_checkpoint="shiitakeMix_v20.safetensors",
    )
