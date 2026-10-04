from __future__ import annotations

from io import BytesIO

from ..context import _load_pillow_image


# {
# 責務: [ImageFailureInspector: 画像を復号し生成失敗と低色分散を保守的に検出する]
# フィールド: [minimum_variance: 低分散判定に使う最小閾値]
# 処理: [1: 画像を縮小してRGB分散を計算する, 2: 問題理由または正常結果を返す]
# }
class ImageFailureInspector:
    """画像のデコード不能・極端な単色化を保守的に検出する。"""

    # {
    # 責務: [__init__: 色分散検査の閾値を初期化する]
    # 処理: [1: 閾値を数値化し0未満を防いで保持する]
    # 引数: [minimum_variance: 低色分散とみなす最小分散値]
    # 戻り値: []
    # }
    def __init__(self, minimum_variance=8.0):
        self.minimum_variance = max(0.0, float(minimum_variance))

    # {
    # 責務: [inspect: 画像bytesのデコード状態と色分散を検査する]
    # 処理: [1: RGB画像へ復号する, 2: 小画像で画素分散を求める, 3: 失敗理由または正常を返す]
    # 引数: [image_bytes: 検査する符号化画像]
    # 戻り値: [異常時の理由辞書、問題がなければNone]
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
    # 責務: [_variance: 数値列の分散を計算する]
    # 処理: [1: 平均値を求める, 2: 平均からの二乗偏差の平均を返す]
    # 引数: [values: 分散を計算する数値列]
    # 戻り値: [母分散]
    # }
    @staticmethod
    def _variance(values):
        average = sum(values) / len(values)
        return sum((value - average) ** 2 for value in values) / len(values)
