"""Image and optional RAW decoders for locally imported capture evidence."""

from __future__ import annotations

import io
from typing import Protocol

from PIL import Image, ImageOps

from .contracts import CaptureFrame


# {
#   責務: [RawFrameDecoder: optional RAW decoderの差し替えinterfaceを定義する]
#   フィールド: [decode_rgb]
#   処理: [keep RAW library optional and injectable]
# }
class RawFrameDecoder(Protocol):
    # {
    #   責務: [decode_rgb: RAW payloadをRGB Pillow imageへ変換する]
    #   処理: [develop one sensor frame without discarding original capture bytes]
    #   引数: [payload: original RAW bytes]
    #   戻り値: [Image.Image: decoded RGB image]
    # }
    def decode_rgb(self, payload: bytes) -> Image.Image: ...


# {
#   責務: [RawpyFrameDecoder: installed rawpy libraryをRAW/DNG RGB変換に使う]
#   フィールド: [none]
#   処理: [import rawpy lazily so RGB-only use has no RAW dependency]
# }
class RawpyFrameDecoder:
    # {
    #   責務: [decode_rgb: rawpy demosaicをRGB画像へ変換する]
    #   処理: [use camera white balance and retain original bytes separately in CaptureFrame]
    #   引数: [payload: DNG or camera RAW encoded bytes]
    #   戻り値: [Image.Image: decoded RGB observation]
    #   エラー: [RuntimeError: rawpy is not installed or RAW decode fails]
    # }
    def decode_rgb(self, payload: bytes) -> Image.Image:
        try:
            import rawpy

            with rawpy.imread(io.BytesIO(payload)) as raw:
                rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
            return Image.fromarray(rgb, mode="RGB")
        except ImportError as error:
            raise RuntimeError("RAW/DNG decoding requires the optional rawpy package") from error


# {
#   責務: [decode_frame: CaptureFrameをoriented RGB pixelsへdecodeする]
#   処理: [route RAW bytes to optional adapter and normalize image orientation]
#   引数: [frame: imported capture, raw_decoder: optional RAW adapter]
#   戻り値: [Image.Image: decoded RGB observation]
#   エラー: [RuntimeError: RAW frame provided without a decoder]
# }
def decode_frame(frame: CaptureFrame, raw_decoder: RawFrameDecoder | None = None) -> Image.Image:
    if frame.media_type == "raw":
        if raw_decoder is None:
            raise RuntimeError(
                "RAW/DNG input is preserved but requires a configured decoder for processing"
            )
        decoded = raw_decoder.decode_rgb(frame.payload)
        return decoded.convert("RGB")
    try:
        with Image.open(io.BytesIO(frame.payload)) as source:
            source.load()
            if source.width * source.height > 16_000_000:
                raise ValueError("capture image exceeds the 16-megapixel processing budget")
            return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"capture image is not safe to decode: {frame.relative_path}") from error
