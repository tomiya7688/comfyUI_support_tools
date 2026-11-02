"""HTTP Tagger adapter used by the new Media Action.

It preserves the existing PixAI contract and the common /tagger/v1 contract.
No proxy discovery, redirects, server startup, Python runtime sharing or app imports.
"""

import base64
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from PIL import Image

from comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend
from comfyui_support_tools.shared.python_tls import create_certifi_context

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


# {
# 責務: [NoRedirect: Tagger HTTP clientでredirect requestを禁止する]
# フィールド: [HTTPRedirectHandler stateのみ。追加fieldなし]
# }
class NoRedirect(HTTPRedirectHandler):
    # {
    #   責務: [redirect_request: redirect先へのrequestを生成しない]
    #   処理: [常にNoneを返しurllib redirect followを止める]
    #   引数: [req/fp/code/msg/headers/newurl: urllib callback values]
    #   戻り値: [None]
    # }
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# {
# 責務: [TaggerTransport: loopback serviceへproxy/redirect-free JSON Tagger requestを送る]
# フィールド: [_opener: proxy無効、redirect拒否、certifi CA限定HTTPS opener]
# }
class TaggerTransport:
    # {
    #   責務: [__init__: proxy無効、redirect拒否、certifi CA bundleを使うopenerを準備する]
    #   処理: [build_openerにProxyHandler空mapping/NoRedirect/filtered HTTPSHandlerを登録する]
    #   引数: [self: transport instance]
    #   戻り値: [なし]
    # }
    def __init__(self):
        self._opener = build_opener(
            ProxyHandler({}),
            NoRedirect(),
            HTTPSHandler(context=create_certifi_context()),
        )

    # {
    #   責務: [_json: bounded JSON responseでTagger endpointへGET/POSTし通信errorをdomain ValueErrorへ変換する]
    #   処理: [optional payloadをJSON化し、1MiB上限、HTTP/network/JSON validationを適用する]
    #   引数: [self: transport, url: endpoint, timeout: seconds, payload: optional JSON request]
    #   戻り値: [Any: decoded response JSON value]
    #   エラー: [ValueError: HTTP/network/oversize/invalid JSON response]
    #   副作用: [HTTP requestを実行しresponse bodyを読む]
    # }
    def _json(self, url, timeout, payload=None):
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
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
            raise ValueError(
                "Tagger APIへ接続できません / timeout。URLとサービスを確認してください"
            ) from None
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("Tagger APIのJSON応答が不正です") from None

    # {
    #   責務: [probe: 選択backendのinterrogator model listを取得し検証する]
    #   処理: [backendを照合してservice interrogators endpointへtimeout上限付きGETを行う]
    #   引数: [self: transport, settings: TaggerSettings]
    #   戻り値: [tuple[str,...]: 重複を除いたmodel names]
    #   エラー: [ValueError: backend不一致、空/不正/過大model list、通信失敗]
    #   副作用: [Tagger interrogators endpointへHTTP GETする]
    # }
    def probe(self, settings):
        resolve_backend(settings.backend, settings.url)
        result = self._json(
            settings.url.rsplit("/", 1)[0] + "/interrogators", min(10, settings.timeout)
        )
        models = result.get("models") if isinstance(result, dict) else result
        if (
            not isinstance(models, list)
            or not models
            or len(models) > 256
            or any(
                not isinstance(x, str)
                or not x.strip()
                or len(x) > 256
                or any(ord(c) < 32 for c in x)
                for x in models
            )
        ):
            raise ValueError("Taggerのモデル一覧が空または不正です")
        return tuple(dict.fromkeys(models))

    # {
    #   責務: [tag: 安定したMediaItem imageを検証後、backend仕様に従いTaggerへ送信する]
    #   処理: [file identity/size/frame/pixelsを照合し、base64 payloadとbackend対応thresholdを作ってPOSTする]
    #   引数: [self: transport, item: scanned MediaItem, settings: TaggerSettings]
    #   戻り値: [Any: Tagger response JSON payload]
    #   エラー: [ValueError: source/backend/image invalid, HTTP/network/response failure]
    #   副作用: [image fileを読みTagger endpointへHTTP POSTする]
    # }
    def tag(self, item, settings):
        backend = resolve_backend(settings.backend, settings.url)
        path = Path(item.path)
        if (
            item.kind != "image"
            or not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
        ):
            raise ValueError("画像ファイルがありません / リンクは送信しません")
        stat = path.stat()
        if stat.st_size != item.size or stat.st_mtime_ns != item.modified_ns:
            raise ValueError("ファイルが変更されています。Browserを再読込してください")
        if not 0 < stat.st_size <= MAX_IMAGE_BYTES:
            raise ValueError("画像サイズは20 MiB以下にしてください")
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        after = path.stat()
        if (
            len(data) != stat.st_size
            or after.st_mtime_ns != stat.st_mtime_ns
            or after.st_size != stat.st_size
        ):
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
        payload = {
            "image": base64.b64encode(data).decode("ascii"),
            "model": settings.model,
            "threshold": settings.threshold,
        }
        if backend.supports_character_threshold:
            payload["character_threshold"] = settings.character_threshold
        return self._json(settings.url, settings.timeout, payload)
