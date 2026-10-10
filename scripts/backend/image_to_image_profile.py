"""Defaults for the Random Img2Img tab, resolved outside its UI module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    if backend == "comfyui":
        a1111_root = _a1111_api_root(a1111_api_url)
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
    if backend == "a1111":
        api_root = _a1111_api_root(a1111_api_url)
        return ImageToImageProfile(
            api_url=f"{api_root}/sdapi/v1/img2img",
            output_dir=a1111_dir / "outputs" / "img2img-images" / "amahane_yukiko_img2img",
            default_checkpoint="rinIllusionRNSFW_v20",
            default_tagger_name="A1111 standard",
            default_tagger_url=f"{api_root}/sdapi/v1/interrogate",
            tagger_presets=(
                ("A1111 standard", f"{api_root}/sdapi/v1/interrogate"),
                ("PixAI v0.9", pixai_tagger_url),
            ),
            usage_note="",
        )
    raise ValueError(f"Unsupported image-to-image profile backend: {backend}")


# {
#   責務: [_a1111_api_root: A1111のbase URLまたはAPI endpointからAPI rootを取り出す]
#   処理: [既知endpoint suffixを取り除き末尾slashを正規化する]
#   引数: [api_url: 設定されたA1111 API URL]
#   戻り値: [str: API root]
# }
def _a1111_api_root(api_url: str) -> str:
    root = api_url.strip().rstrip("/")
    for suffix in ("/sdapi/v1/img2img", "/sdapi/v1/txt2img", "/sdapi/v1", "/sdapi"):
        if root.endswith(suffix):
            return root[: -len(suffix)]
    return root
