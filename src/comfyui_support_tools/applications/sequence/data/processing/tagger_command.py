"""GUI-independent Tagger HTTP command for local sequence steps."""

from __future__ import annotations

import base64
from dataclasses import asdict
from io import BytesIO
import ipaddress
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from PIL import Image

from comfyui_support_tools.applications.sequence.data.processing.tagger_result_writer import (
    TaggerResultWriter,
)
from comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend
from comfyui_support_tools.shared.python_tls import create_certifi_context
from comfyui_support_tools.shared.tag_result_normalizer import parse_tag_result

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TIMEOUT = 600


# {
# 責務: [_NoRedirect: urllib openerがTagger endpoint redirectを追跡しないようにする]
# フィールド: [HTTPRedirectHandlerの標準設定。追加instance stateなし]
# }
class _NoRedirect(HTTPRedirectHandler):
    # {
    #   責務: [redirect_request: redirect responseを新しいrequestへ変換しない]
    #   処理: [urllib openerからredirectを拒否させるため常にNoneを返す]
    #   引数: [req/fp/code/msg/headers/newurl: HTTPRedirectHandler callback values]
    #   戻り値: [None: redirect follow-up requestを生成しない]
    # }
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# {
# 責務: [TaggerCommand: local compatible Tagger serviceへimageを送りnormalized resultを作る]
# フィールド: [_result_writer: optional sidecar writer, _timeout: timeout, _opener: proxy-free HTTPS opener]
# }
class TaggerCommand:
    """Send one image to a compatible Tagger service running on this machine."""

    # {
    #   責務: [__init__: timeoutを検証し、proxyを使わないfiltered-CA HTTPS openerを準備する]
    #   処理: [result writerとtimeoutを保持し、redirect禁止handlerを含むurllib openerを作る]
    #   引数: [self: command instance, timeout: request timeout seconds]
    #   戻り値: [なし]
    #   エラー: [ValueError: timeoutが0より大きくMAX_TIMEOUT以下でない]
    # }
    def __init__(self, timeout: float = 60.0) -> None:
        self._result_writer = TaggerResultWriter()
        self._validate_timeout(timeout)
        self._timeout = timeout
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirect(),
            HTTPSHandler(context=create_certifi_context()),
        )

    # {
    #   責務: [__call__: imageを読みTaggerへ送り、normalized tagsと任意sidecar pathを返す]
    #   処理: [image/path/backend/threshold検証、HTTP POST、response正規化、重複出力path拒否、任意writeを行う]
    #   引数: [inputs: image/model/url/backend/threshold/output settings, _context: runner context（未使用）]
    #   戻り値: [backend/model/tags/tag_text/caption/rating/metadata/resultと任意txt_path/metadata_path]
    #   エラー: [ValueError: inputやimage/URL invalid, RuntimeError: HTTP/response/JSON failure]
    #   副作用: [TaggerへHTTP POSTし、明示されたsidecar fileをatomic writeする]
    # }
    def __call__(self, inputs: Mapping[str, Any], _context: Mapping[str, Any]) -> Mapping[str, Any]:
        image_path = self._required_text(inputs, "image")
        model = self._required_text(inputs, "model")
        backend_id = inputs.get("backend", "auto_http")
        url = self._validate_url(inputs.get("url"), backend_id)
        threshold = self._threshold(inputs.get("threshold", 0.35), "threshold")
        character_threshold = self._threshold(
            inputs.get("character_threshold", 0.85), "character_threshold"
        )
        timeout = inputs.get("timeout", self._timeout)
        self._validate_timeout(timeout)
        txt_value = inputs.get("txt_output")
        metadata_value = inputs.get("metadata_output")
        txt_output = (
            self._result_writer.validate_path(txt_value, "txt_output")
            if txt_value is not None
            else None
        )
        metadata_output = (
            self._result_writer.validate_path(metadata_value, "metadata_output")
            if metadata_value is not None
            else None
        )
        image = self._read_image(Path(image_path))
        backend = resolve_backend(backend_id, url)
        payload = {
            "image": base64.b64encode(image).decode("ascii"),
            "model": model,
            "threshold": threshold,
        }
        if backend.supports_character_threshold:
            payload["character_threshold"] = character_threshold
        raw_result = self._post_json(url, payload, timeout)
        result = parse_tag_result(
            raw_result, threshold, character_threshold, backend.id, url, model
        )
        normalized = self._normalized_mapping(result)
        tags = (
            *result.content_tags,
            *result.character_tags,
            *result.copyright_tags,
        )
        tag_text = ", ".join(tags)
        if (
            txt_output is not None
            and metadata_output is not None
            and txt_output.resolve(strict=False) == metadata_output.resolve(strict=False)
        ):
            raise ValueError("txt_output and metadata_output must be different paths")
        outputs = {
            "backend": result.backend,
            "model": result.model,
            "tags": list(tags),
            "tag_text": tag_text,
            "caption": result.caption,
            "caption_text": result.caption or tag_text,
            "rating": result.rating,
            "metadata": normalized,
            "result": normalized,
        }

        if txt_output is not None:
            self._result_writer.write_text(txt_output, tag_text)
            outputs["txt_path"] = str(txt_output)
        if metadata_output is not None:
            self._result_writer.write_metadata(metadata_output, normalized)
            outputs["metadata_path"] = str(metadata_output)
        return outputs

    # {
    #   責務: [_required_text: Tagger inputsから必須のtrim済み文字列を取得する]
    #   処理: [key値がnon-empty stringであることを確認する]
    #   引数: [inputs: command input mapping, key: 必須field名]
    #   戻り値: [trimmed text]
    #   エラー: [ValueError: 値が空またはstring型でない]
    # }
    @staticmethod
    def _required_text(inputs: Mapping[str, Any], key: str) -> str:
        value = inputs.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()

    # {
    #   責務: [_threshold: inclusive 0..1範囲のscore thresholdをfloat化する]
    #   処理: [boolと非数値、範囲外値を拒否する]
    #   引数: [value: threshold候補, name: error message用field名]
    #   戻り値: [float: validated threshold]
    #   エラー: [ValueError: 値が0から1の範囲外]
    # }
    @staticmethod
    def _threshold(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
        return float(value)

    # {
    #   責務: [_validate_timeout: request timeoutを正の数かつMAX_TIMEOUT以下に制限する]
    #   処理: [bool、非数値、0以下、上限超過を拒否する]
    #   引数: [value: timeout候補]
    #   戻り値: [なし]
    #   エラー: [ValueError: timeoutが許容範囲外]
    # }
    @staticmethod
    def _validate_timeout(value: Any) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < value <= MAX_TIMEOUT
        ):
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")

    # {
    #   責務: [_validate_url: backend固有endpoint suffixを持つloopback Tagger URLを検証する]
    #   処理: [HTTP(S), localhost/loopback, credential/query/fragment/port条件を確認しresolve_backendでsuffix照合する]
    #   引数: [value: URL候補, backend_id: explicit backendまたはauto_http]
    #   戻り値: [endpoint: 検証済みURL string]
    #   エラー: [ValueError: URL条件、portまたはbackend endpointが不正]
    # }
    @staticmethod
    def _validate_url(value: Any, backend_id: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("url must be a local HTTP(S) Tagger endpoint URL")
        endpoint = value.strip()
        parsed = urlsplit(endpoint)
        try:
            port = parsed.port
            host = parsed.hostname or ""
            local_host = host.lower() == "localhost" or (
                bool(host) and ipaddress.ip_address(host).is_loopback
            )
        except ValueError:
            local_host = False
            port = None
        if (
            parsed.scheme not in {"http", "https"}
            or not local_host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Tagger URL must target localhost/loopback without credentials, query, or fragment"
            )
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("url contains an invalid port")
        resolve_backend(backend_id, endpoint)
        return endpoint

    # {
    #   責務: [_read_image: absolute regular image fileをsize/pixel/frame limit付きで読み検証する]
    #   処理: [symlink拒否、20 MiB上限、read中stat安定性、40MP以下かつsingle-frame画像のdecode verifyを行う]
    #   引数: [path: image file path]
    #   戻り値: [data: 検証済みimage bytes]
    #   エラー: [ValueError: path/file/size/contentが許容外、fileが読み取り中に変化]
    #   副作用: [fileをbinary modeで読む]
    # }
    @staticmethod
    def _read_image(path: Path) -> bytes:
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("image must be an existing absolute file, not a symbolic link")
        before = path.stat()
        if not 0 < before.st_size <= MAX_IMAGE_BYTES:
            raise ValueError("image must be between 1 byte and 20 MiB")
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        after = path.stat()
        if (
            len(data) != before.st_size
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise ValueError("image changed while it was being read")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image exceeds 40 megapixels")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("animated or multi-frame images are not supported")
                image.verify()
        except (ValueError, OSError):
            raise ValueError("image is invalid, too large, or has multiple frames") from None
        return data

    # {
    #   責務: [_post_json: redirectを追わず応答サイズ/JSONを制限してTaggerへPOSTする]
    #   処理: [NaN禁止JSON requestを送信し、HTTP/network errorを隠してbounded bodyをparseする]
    #   引数: [self: command instance, url: Tagger endpoint, payload: request mapping, timeout: request timeout]
    #   戻り値: [Any: decoded JSON response]
    #   エラー: [RuntimeError: HTTP/network failure、response 1MiB超過、invalid JSON]
    #   副作用: [HTTP POSTを実行し応答bodyを読み込む]
    # }
    def _post_json(self, url: str, payload: Mapping[str, Any], timeout: float) -> Any:
        request = Request(
            url,
            data=json.dumps(payload, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            code = error.code
            error.close()
            raise RuntimeError(
                f"Tagger API returned HTTP {code}; redirects are not followed"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Could not reach Tagger API; check the URL and service") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Tagger API response exceeds 1 MiB")
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=self._reject_json_constant)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            raise RuntimeError("Tagger API returned invalid JSON") from None

    # {
    #   責務: [_reject_json_constant: JSON decoderがNaN/Infinityを受理しないようにする]
    #   処理: [parse_constant callback値をValueErrorとして拒否する]
    #   引数: [value: decoderが検出した非標準numeric token]
    #   戻り値: [なし]
    #   エラー: [ValueError: JSON tokenがRFC JSON numberでない]
    # }
    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON constant: {value}")

    # {
    #   責務: [_normalized_mapping: dataclass resultをsidecar/API出力用JSON containerへ変換する]
    #   処理: [asdict後、tag tupleとscore record tupleをlistへ変換する]
    #   引数: [result: NormalizedTagResult]
    #   戻り値: [dict: JSON-compatible normalized result mapping]
    # }
    @staticmethod
    def _normalized_mapping(result: Any) -> dict[str, Any]:
        values = asdict(result)
        for key in ("content_tags", "character_tags", "copyright_tags"):
            values[key] = list(values[key])
        for key in ("content_scores", "character_scores", "rating_scores"):
            values[key] = list(values[key])
        return values
