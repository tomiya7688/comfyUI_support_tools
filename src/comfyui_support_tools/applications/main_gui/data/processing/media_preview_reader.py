"""Local Pillow/OpenCV previews with a versioned, byte-bounded LRU cache."""

from collections import OrderedDict
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageOps
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.contracts.media_preview import MediaPreview

MAX_PIXELS = 40_000_000


# {
# 責務: [MediaPreviewReader: Pillow/OpenCVでbounded preview bytesを読みLRU cacheに保持する]
# フィールド: [cache, max_entries, max_bytes, cache_bytes]
# }
class MediaPreviewReader:
    """Used only by the decoder worker; GUI images are created by UI Processing."""

    # {
    #   責務: [__init__: byte/entry上限付きLRU cache stateを作る]
    #   処理: [cache上限を保持しOrderedDictとbyte counterを初期化する]
    #   引数: [self: reader, max_entries: record上限, max_bytes: PNG byte総量上限]
    #   戻り値: [なし]
    # }
    def __init__(self, max_entries: int = 128, max_bytes: int = 16 * 1024 * 1024):
        self.cache = OrderedDict()
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.cache_bytes = 0

    # {
    #   責務: [read: MediaItemの画像またはvideo frameをPNG preview contractとして返す]
    #   処理: [edge/fraction検証、versioned LRU key照合、image/video decode、PNG化、cache evictionを行う]
    #   引数: [self: reader, item: source MediaItem, edge: 対応寸法128/480, fraction: 0..1 video seek位置]
    #   戻り値: [MediaPreview: bounded PNG/dimensions/durationまたはerror]
    #   副作用: [media fileをreadしLRU cacheを更新する]
    # }
    def read(self, item: MediaItem, edge: int, fraction: float = 0.0) -> MediaPreview:
        if edge not in (128, 480) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
            return MediaPreview(item.id, error="プレビュー条件が不正です")
        try:
            path = Path(item.path)
            if not path.is_file() or path.is_symlink():
                raise ValueError("ファイルがありません / リンクはプレビューしません")
            stat = path.stat()
            key = (item.id, stat.st_size, stat.st_mtime_ns, edge, round(fraction, 3))
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            if item.kind == "image":
                with Image.open(path) as source:
                    width, height = source.size
                    if width * height > MAX_PIXELS:
                        raise ValueError("画像が大きすぎるためプレビューを省略しました")
                    orientation = source.getexif().get(274, 1)
                    source.thumbnail((edge, edge))
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    if orientation in (5, 6, 7, 8):
                        width, height = height, width
                duration = 0.0
            else:
                image, width, height, duration = self._video(item.path, fraction)
                image.thumbnail((edge, edge))
            output = BytesIO()
            image.save(output, format="PNG")
            result = MediaPreview(item.id, output.getvalue(), width, height, duration)
            self.cache[key] = result
            self.cache_bytes += len(result.png)
            while self.cache and (
                len(self.cache) > self.max_entries or self.cache_bytes > self.max_bytes
            ):
                self.cache_bytes -= len(self.cache.popitem(last=False)[1].png)
            return result
        except Exception as exc:
            # Broken files/codecs stay visible in the browser; errors are data,
            # not uncaught callbacks. Never execute a CLI/player to recover.
            return MediaPreview(item.id, error=f"プレビュー不可: {type(exc).__name__}: {exc}")

    # {
    #   責務: [_video: OpenCVでvideoをseekし一つのframeとdurationを取得する]
    #   処理: [capture open/dimensions/fps/frame countを検証しfraction frameをdecodeしてRGB Imageへ変換する]
    #   引数: [path: video file path, fraction: requested seek position 0..1]
    #   戻り値: [Pillow RGB image, width, height, duration seconds]
    #   エラー: [ValueError: video/codec/size/seek/frame readが対応外]
    #   副作用: [OpenCV captureを開きfinallyでreleaseする]
    # }
    @staticmethod
    def _video(path: str, fraction: float):
        import cv2

        capture = cv2.VideoCapture(path)
        try:
            if not capture.isOpened():
                raise ValueError("動画を開けません（形式・コーデックを確認してください）")
            width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
            if width * height > MAX_PIXELS:
                raise ValueError("動画フレームが大きすぎるため省略しました")
            fps = capture.get(cv2.CAP_PROP_FPS)
            frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if not math.isfinite(frames) or frames < 0:
                frames = 0
            duration = frames / fps if math.isfinite(fps) and fps > 0 else 0.0
            if fraction and frames > 1:
                if not capture.set(cv2.CAP_PROP_POS_FRAMES, int((frames - 1) * fraction)):
                    raise ValueError("この動画は指定位置のプレビューに対応していません")
            ok, frame = capture.read()
            if not ok:
                raise ValueError("動画フレームを読み取れません")
            height, width = frame.shape[:2]
            if width * height > MAX_PIXELS:
                raise ValueError("動画フレームが大きすぎるため省略しました")
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), width, height, duration
        finally:
            capture.release()
