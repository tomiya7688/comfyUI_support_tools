"""HTTP contract already used by FolderTaggerTab; never starts its server.

Only user-configured HTTP(S) URLs. No proxy discovery, redirects or app imports.
HTTP responses/images have explicit byte limits; errors never echo server bodies.
"""
import base64
from io import BytesIO
import json
import math
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from PIL import Image
import certifi

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TaggerTransport:
    def __init__(self):
        self._opener = build_opener(ProxyHandler({}), NoRedirect(),
                                   HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def _json(self, url, timeout, payload=None):
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("Tagger API応答が上限1 MiBを超えています")
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise ValueError(f"Tagger API: HTTP {code}（redirectは追跡しません）") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Tagger APIへ接続できません / timeout。URLとサービスを確認してください") from None
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("Tagger APIのJSON応答が不正です") from None

    def probe(self, settings):
        result = self._json(settings.url.rsplit("/", 1)[0] + "/interrogators", min(10, settings.timeout))
        models = result.get("models") if isinstance(result, dict) else result
        if (not isinstance(models, list) or not models or len(models) > 256
                or any(not isinstance(x, str) or not x.strip() or len(x) > 256
                       or any(ord(c) < 32 for c in x) for x in models)):
            raise ValueError("Taggerのモデル一覧が空または不正です")
        return tuple(dict.fromkeys(models))

    def tag(self, item, settings):
        path = Path(item.path)
        if item.kind != "image" or not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("画像ファイルがありません / リンクは送信しません")
        stat = path.stat()
        if stat.st_size != item.size or stat.st_mtime_ns != item.modified_ns:
            raise ValueError("ファイルが変更されています。Browserを再読込してください")
        if not 0 < stat.st_size <= MAX_IMAGE_BYTES:
            raise ValueError("画像サイズは20 MiB以下にしてください")
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        after = path.stat()
        if len(data) != stat.st_size or after.st_mtime_ns != stat.st_mtime_ns or after.st_size != stat.st_size:
            raise ValueError("読込中にファイルが変更されました")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError("40MPを超える画像は対象外です")
                if getattr(image, "n_frames", 1) > 1:
                    raise ValueError("複数フレーム画像は対象外です。静止画へ変換してください")
                image.verify()
        except Exception:
            raise ValueError("破損・巨大・複数フレーム画像はTag Actionへ送信できません") from None
        payload = {"image": base64.b64encode(data).decode("ascii"),
                   "model": settings.model, "threshold": settings.threshold}
        if "/pixai/v1/" in settings.url:
            payload["character_threshold"] = settings.character_threshold
        return self._json(settings.url, settings.timeout, payload)
