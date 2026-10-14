"""Defaults for the Random Img2Img tab, resolved outside its UI module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .a1111_api_url import normalize_a1111_api_root


# {
#   責務: [ImageToImageProfile: Random Img2Imgタブに必要な起動既定値を保持する]
#   フィールド: [API URL, 出力先, checkpoint, Tagger既定値, 案内文]
# }
@dataclass(frozen=True)
class ImageToImageProfile:
    api_url: str
    output_dir: Path
    default_checkpoint: str
    default_tagger_name: str
    default_tagger_url: str
    tagger_presets: tuple[tuple[str, str], ...]
    usage_note: str


# {
#   責務: [create_image_to_image_profile: 選択backend向けのRandom Img2Img既定値を作成する]
#   処理: [backend設定からAPI URL・出力先・既定モデルとTaggerを構成して返す]
#   引数: [backend: backend識別子, a1111_api_url: WebUI API base URL, comfyui_api_url: ComfyUI API base URL, a1111_dir: WebUI runtime root, runtime_dir: 選択backend runtime root, pixai_tagger_url: PixAI Tagger URL]
#   戻り値: [ImageToImageProfile: Random Img2Img既定値]
#   エラー: [ValueError: 未対応backendが渡された場合]
# }
def create_image_to_image_profile(
    backend: str,
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    pixai_tagger_url: str,
) -> ImageToImageProfile:
    from .generation_backend_registry import generation_backend_profile_factory

    factory = generation_backend_profile_factory(backend, "image_to_image")
    return factory(
        a1111_api_url,
        comfyui_api_url,
        a1111_dir,
        runtime_dir,
        pixai_tagger_url,
    )


# {
#   責務: [create_a1111_image_to_image_profile: A1111向けImg2Img既定値を作る]
#   処理: [A1111 API endpoint・保存先・既定checkpoint・taggerを設定する]
#   引数: [a1111_api_url: A1111 API URL, comfyui_api_url: 未使用の共通互換引数, a1111_dir: A1111 runtime root, runtime_dir: 未使用の共通互換引数, pixai_tagger_url: PixAI Tagger URL]
#   戻り値: [ImageToImageProfile: A1111のImg2Img既定値]
# }
def create_a1111_image_to_image_profile(
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    pixai_tagger_url: str,
) -> ImageToImageProfile:
    del comfyui_api_url, runtime_dir
    api_root = normalize_a1111_api_root(a1111_api_url)
    interrogate_url = f"{api_root}/sdapi/v1/interrogate"
    return ImageToImageProfile(
        api_url=f"{api_root}/sdapi/v1/img2img",
        output_dir=a1111_dir / "outputs" / "img2img-images" / "amahane_yukiko_img2img",
        default_checkpoint="rinIllusionRNSFW_v20",
        default_tagger_name="A1111 standard",
        default_tagger_url=interrogate_url,
        tagger_presets=(
            ("A1111 standard", interrogate_url),
            ("PixAI v0.9", pixai_tagger_url),
        ),
        usage_note="",
    )


# {
#   責務: [create_comfyui_image_to_image_profile: ComfyUI向けImg2Img既定値を作る]
#   処理: [ComfyUI API・保存先・既定checkpoint・taggerを設定する]
#   引数: [a1111_api_url: A1111 API URL, comfyui_api_url: ComfyUI API URL, a1111_dir: 未使用の共通互換引数, runtime_dir: ComfyUI runtime root, pixai_tagger_url: PixAI Tagger URL]
#   戻り値: [ImageToImageProfile: ComfyUIのImg2Img既定値]
# }
def create_comfyui_image_to_image_profile(
    a1111_api_url: str,
    comfyui_api_url: str,
    a1111_dir: Path,
    runtime_dir: Path,
    pixai_tagger_url: str,
) -> ImageToImageProfile:
    del a1111_dir
    a1111_root = normalize_a1111_api_root(a1111_api_url)
    return ImageToImageProfile(
        api_url=comfyui_api_url.strip().rstrip("/"),
        output_dir=runtime_dir / "output" / "KadokaTools_img2img",
        default_checkpoint="shiitakeMix_v20.safetensors",
        default_tagger_name="PixAI v0.9",
        default_tagger_url=pixai_tagger_url,
        tagger_presets=(
            ("A1111 standard", f"{a1111_root}/sdapi/v1/interrogate"),
            ("PixAI v0.9", pixai_tagger_url),
        ),
        usage_note="※ タグ取得にはPixAI API、生成にはComfyUI APIを使います。",
    )
