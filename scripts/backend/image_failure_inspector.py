from __future__ import annotations

from io import BytesIO

from ..context import _load_pillow_image


# {
#   責務: [ImageFailureInspector: decode errors and extremely low-variance imagesをconservatively detectする]
#   処理: [store a lower-bounded variance threshold and inspect bounded previews]
#   フィールド: [minimum_variance threshold]
# }
class ImageFailureInspector:
    """画像のデコード不能・極端な単色化を保守的に検出する。"""

    # {
    #   責務: [__init__: minimum color variance thresholdをnormalizeして保存する]
    #   処理: [convert to float and clamp at zero]
    #   引数: [minimum_variance]
    #   戻り値: [処理結果]
    # }
    def __init__(self, minimum_variance=8.0):
        self.minimum_variance = max(0.0, float(minimum_variance))

    # {
    #   責務: [inspect: encoded image bytesからdecode failure, empty content, or low varianceをinspectする]
    #   処理: [decode with Pillow, downscale to 256px, compute CPU channel variance, and return failure evidence or None]
    #   引数: [image_bytes]
    #   戻り値: [処理結果]
    # }
    def inspect(self, image_bytes):
        try:
            image_module = _load_pillow_image()
            with image_module.open(BytesIO(image_bytes)) as source:
                image = source.convert("RGB")
        except Exception as error:
            return {"reason": "image_decode_error", "detail": str(error)}
        image.thumbnail((256, 256))
        pixels = list(image.getdata())
        if not pixels:
            return {"reason": "empty_image", "detail": "decoded image has no pixels"}
        channels = tuple(zip(*pixels))
        variance = sum(self._variance(channel) for channel in channels) / len(channels)
        if variance < self.minimum_variance:
            return {
                "reason": "extremely_low_color_variance",
                "detail": f"color variance {variance:.3f} is below {self.minimum_variance:.3f}",
                "color_variance": round(variance, 4),
            }
        return None

    # {
    #   責務: [_variance: one channel valuesのpopulation varianceをcalculateする]
    #   処理: [compute arithmetic mean and mean squared deviation]
    #   引数: [values]
    #   戻り値: [処理結果]
    # }
    @staticmethod
    def _variance(values):
        average = sum(values) / len(values)
        return sum((value - average) ** 2 for value in values) / len(values)
