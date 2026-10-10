"""Backend-specific defaults for the Random Image generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
#   責務: [create_image_generation_profile: Random Image用backend profileを作成する]
#   処理: [1: backendを検証する, 2: API URL・保存先・checkpointを選択する, 3: profileを返す]
#   引数: [backend: 選択中backend, a1111_api_url: A1111のAPI base URL, comfyui_api_url: ComfyUI API base URL, a1111_dir: A1111 runtime root, runtime_dir: 選択backend runtime root, date_folder: 日付別保存フォルダー名]
#   戻り値: [ImageGenerationProfile: Random Imageのbackend既定値]
#   エラー: [ValueError: 未対応backendが渡された場合]
# }
def create_image_generation_profile(
    backend: str,
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    date_folder: str,
) -> ImageGenerationProfile:
    if backend == "comfyui":
        return ImageGenerationProfile(
            backend=backend,
            api_url=comfyui_api_url.strip().rstrip("/"),
            output_dir=runtime_dir / "output" / "KadokaTools" / date_folder,
            default_checkpoint="shiitakeMix_v20.safetensors",
        )
    if backend == "a1111":
        api_root = a1111_api_url.strip().rstrip("/")
        if api_root.endswith("/sdapi/v1/txt2img"):
            api_url = api_root
        elif api_root.endswith("/sdapi/v1"):
            api_url = f"{api_root}/txt2img"
        elif api_root.endswith("/sdapi"):
            api_url = f"{api_root}/v1/txt2img"
        else:
            api_url = f"{api_root}/sdapi/v1/txt2img"
        return ImageGenerationProfile(
            backend=backend,
            api_url=api_url,
            output_dir=a1111_dir / "outputs" / "txt2img-images" / date_folder,
            default_checkpoint="rinIllusionRNSFW_v30",
        )
    raise ValueError(f"Unsupported generation profile backend: {backend}")
