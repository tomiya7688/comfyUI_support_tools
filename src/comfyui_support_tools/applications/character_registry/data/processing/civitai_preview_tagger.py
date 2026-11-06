"""Fetch selected Civitai preview images and ask a loopback Tagger for suggestions."""

import base64
import json
import math
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from PIL import Image

from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)
from src.comfyui_support_tools.shared.contracts.civitai_preview_image import (
    MAX_TAGGER_ANALYSIS_IMAGES,
)
from src.comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings
from src.comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend
from src.comfyui_support_tools.shared.python_tls import create_certifi_context
from src.comfyui_support_tools.shared.tag_result_normalizer import parse_tag_result

MAX_PREVIEW_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TAGGER_RESPONSE_BYTES = 1024 * 1024
MAX_PIXELS = 40_000_000
REQUEST_TIMEOUT_SECONDS = 30
_ALLOWED_IMAGE_HOSTS = {"image.civitai.com", "imagecache.civitai.com"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


# {
#   責務: [_NoRedirect: preview/Tagger API通信でHTTP redirectを拒否する]
#   フィールド: [HTTPRedirectHandlerのredirect policy]
# }
class _NoRedirect(HTTPRedirectHandler):
    # {
    #   責務: [redirect_request: 画像/Tagger通信のredirect追跡を拒否する]
    #   処理: [redirect先へpayloadや画像取得を転送しない]
    #   引数: [self: redirect handler, requestとresponse情報]
    #   戻り値: [None: redirectを追跡しない]
    # }
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


# {
#   責務: [_validate_settings: Tagger endpointをloopback APIと選択backendへ制限する]
#   処理: [必須modelとtimeoutを確認し, credential/query/fragmentを含まないloopback URLを検証する]
#   引数: [settings: 選択したTagger設定]
#   戻り値: [str: 解決済みbackend ID]
#   エラー: [ValueError: 設定が空, loopback以外, または不正な場合]
# }
def _validate_settings(settings: TaggerSettings) -> str:
    if not isinstance(settings, TaggerSettings):
        raise ValueError("tagger_settingsはTaggerSettingsで指定してください")
    if (
        not isinstance(settings.model, str)
        or len(settings.model) > 256
        or any(ord(character) < 32 for character in settings.model)
    ):
        raise ValueError("Tagger modelは256文字以下で指定してください")
    if (
        isinstance(settings.timeout, bool)
        or not isinstance(settings.timeout, (int, float))
        or not math.isfinite(settings.timeout)
        or not 0 < settings.timeout <= REQUEST_TIMEOUT_SECONDS
    ):
        raise ValueError("Tagger timeoutは30秒以下で指定してください")
    for threshold in (settings.threshold, settings.character_threshold):
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("Tagger thresholdは0〜1の有限値で指定してください")
    if not isinstance(settings.url, str) or len(settings.url) > 2048:
        raise ValueError("Tagger URLは2048文字以下で指定してください")
    try:
        parsed = urlsplit(settings.url)
    except ValueError as error:
        raise ValueError("Tagger loopback URLの形式が不正です") from error
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Tagger loopback URLのportが不正です") from error
    if (
        parsed.scheme not in {"http", "https"}
        or hostname not in _LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Tagger endpointはcredentialなしのloopback URLにしてください")
    try:
        backend = resolve_backend(settings.backend, settings.url)
    except ValueError as error:
        raise ValueError(f"Tagger endpoint設定が不正です: {error}") from error
    return backend.id


# {
#   責務: [_read_limited: response streamを上限byte数まで読み取る]
#   処理: [上限+1byteを読み, 超過を拒否する]
#   引数: [response: urllib response, maximum: 許容byte数]
#   戻り値: [bytes: 読み取った内容]
#   エラー: [ValueError: 上限を超過した場合]
# }
def _read_limited(response, maximum: int) -> bytes:
    data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"remote responseが上限{maximum} bytesを超えています")
    return data


# {
#   責務: [_open_direct: proxy/redirectなしのurllib openerを作る]
#   処理: [proxyを無効化し, redirectを拒否してcertifi TLS contextを設定する]
#   引数: []
#   戻り値: [OpenerDirector: 直接接続opener]
# }
def _open_direct():
    return build_opener(
        ProxyHandler({}),
        _NoRedirect(),
        HTTPSHandler(context=create_certifi_context()),
    )


# {
#   責務: [_fetch_preview_image: allowlist内のCivitai CDN画像を上限付きで取得する]
#   処理: [画像URLを再検証してGETし, MIME/byte数/画像寸法/frame数を確認する]
#   引数: [image_url: Civitai CDN URL, opener: direct urllib opener]
#   戻り値: [bytes: Taggerへ一時送信する画像内容]
#   エラー: [ValueError: host, HTTP, MIME, byte数, 画像形式が不正な場合]
# }
def _fetch_preview_image(image_url: str, opener) -> bytes:
    try:
        parsed = urlsplit(image_url)
    except ValueError as error:
        raise ValueError("Civitai画像URLの形式が不正です") from error
    host = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or host not in _ALLOWED_IMAGE_HOSTS
        or parsed.netloc.casefold() != host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("Civitai画像URLは許可済みCDNのHTTPS URLである必要があります")
    request = Request(
        image_url, headers={"Accept": "image/*", "User-Agent": "comfyUI-support-tools/1.0"}
    )
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise ValueError("Civitai preview responseはimage MIMEではありません")
            data = _read_limited(response, MAX_PREVIEW_IMAGE_BYTES)
    except HTTPError as error:
        error.close()
        raise ValueError(f"Civitai preview API: HTTP {error.code}") from error
    except (TimeoutError, URLError, OSError) as error:
        raise ValueError(f"Civitai previewに接続できません: {error}") from error
    if not data:
        raise ValueError("Civitai preview imageが空です")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("40MPを超えるCivitai previewはTaggerに送信できません")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("複数フレーム画像はTaggerに送信できません")
            image.verify()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Civitai preview画像が破損または過大です") from error
    return data


# {
#   責務: [_request_json: loopback Taggerへbounded JSON requestを送る]
#   処理: [任意payloadをPOSTまたはGETし, JSON応答byte数/schemaを検証する]
#   引数: [opener: direct opener, url: loopback URL, timeout: seconds, payload: POST内容]
#   戻り値: [object: decoded JSON]
#   エラー: [ValueError: HTTP, timeout, JSON, byte limit error]
# }
def _request_json(opener, url: str, timeout: float, payload: dict[str, object] | None = None):
    body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            data = _read_limited(response, MAX_TAGGER_RESPONSE_BYTES)
        return json.loads(data.decode("utf-8"))
    except HTTPError as error:
        error.close()
        raise ValueError(f"Tagger API: HTTP {error.code}（redirectは追跡しません）") from error
    except (TimeoutError, URLError, OSError) as error:
        raise ValueError(f"Tagger loopback APIへ接続できません: {error}") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Tagger APIのJSON応答が不正です") from error


# {
#   責務: [_select_model: Taggerが利用可能と返したmodelを検証して決定する]
#   処理: [空指定は先頭modelを選び, 明示指定は一覧に一致する場合だけ返す]
#   引数: [opener: direct opener, settings: Tagger endpoint/model/timeout]
#   戻り値: [str: Tagger model名]
#   エラー: [ValueError: model一覧が空/不正または指定modelが見つからない場合]
# }
def _select_model(opener, settings: TaggerSettings) -> str:
    endpoint = settings.url.rsplit("/", 1)[0] + "/interrogators"
    response = _request_json(opener, endpoint, min(10, settings.timeout))
    models = response.get("models") if isinstance(response, dict) else response
    if (
        not isinstance(models, list)
        or not models
        or len(models) > 256
        or any(
            not isinstance(model, str)
            or not model.strip()
            or len(model) > 256
            or any(ord(character) < 32 for character in model)
            for model in models
        )
    ):
        raise ValueError("Taggerのmodel一覧が空または不正です")
    unique_models = tuple(dict.fromkeys(model.strip() for model in models))
    if settings.model:
        if settings.model not in unique_models:
            raise ValueError("指定されたTagger modelが利用可能model一覧にありません")
        return settings.model
    return unique_models[0]


# {
#   責務: [_tag_image: 1枚のCivitai preview画像をloopback Taggerで解析する]
#   処理: [image bytesをbase64化してinterrogate endpointへ送り, normalized tag候補を返す]
#   引数: [opener: direct opener, image_data: 画像bytes, settings: Tagger設定, model: 解決model]
#   戻り値: [tuple[str, ...]: generalとcharacter tagを重複なしで返す]
#   エラー: [ValueError: Tagger応答が不正または認識できない場合]
# }
def _tag_image(opener, image_data: bytes, settings: TaggerSettings, model: str) -> tuple[str, ...]:
    backend = resolve_backend(settings.backend, settings.url)
    payload: dict[str, object] = {
        "image": base64.b64encode(image_data).decode("ascii"),
        "model": model,
        "threshold": settings.threshold,
    }
    if backend.supports_character_threshold:
        payload["character_threshold"] = settings.character_threshold
    response = _request_json(opener, settings.url, settings.timeout, payload)
    result = parse_tag_result(
        response,
        settings.threshold,
        settings.character_threshold,
        backend.id,
        settings.url,
        model,
    )
    return tuple(dict.fromkeys((*result.content_tags, *result.character_tags)))


# {
#   責務: [tag_civitai_preview_images: 選択版の上限付きプレビュー画像からTagger提案assetを作る]
#   処理: [最多MAX_TAGGER_ANALYSIS_IMAGES枚を一時取得しloopback Taggerへ送り, unknown-rights assetを返す]
#   引数: [metadata: 選択version metadata, settings: loopback Tagger設定]
#   戻り値: [tuple[CharacterSourceAsset, ...]: taxonomy previewに合流するtag source]
#   エラー: [ValueError: 設定/画像/Tagger response不正, RuntimeError: 処理対象画像がない場合]
# }
def tag_civitai_preview_images(
    metadata: CivitaiLoraVersionMetadata,
    settings: TaggerSettings,
) -> tuple[CharacterSourceAsset, ...]:
    if not isinstance(metadata, CivitaiLoraVersionMetadata):
        raise ValueError("metadataはCivitaiLoraVersionMetadataで指定してください")
    backend_id = _validate_settings(settings)
    selected_images = metadata.preview_images[:MAX_TAGGER_ANALYSIS_IMAGES]
    if not selected_images:
        raise RuntimeError("選択したCivitai versionに閲覧可能なプレビュー画像がありません")
    opener = _open_direct()
    model = _select_model(opener, settings)
    candidate = metadata.candidate
    assets: list[CharacterSourceAsset] = []
    for preview_image in selected_images:
        image_data = _fetch_preview_image(preview_image.url, opener)
        tags = _tag_image(opener, image_data, settings, model)
        source_reference = (
            f"civitai://models/{candidate.model_id}/versions/{candidate.version_id}"
            f"/images/{preview_image.image_id}/tagger"
        )
        assets.append(
            CharacterSourceAsset(
                caption_file=source_reference,
                image_file=None,
                tags=tags,
                outfit_id=None,
                source_url=candidate.source_url,
                source_work_id=f"{candidate.model_id}:{candidate.version_id}",
                license_status="unknown",
                training_permission="unknown",
                source_metadata=(
                    ("tag_source", "civitai_preview_tagger"),
                    ("preview_image_id", str(preview_image.image_id)),
                    (
                        "nsfw_level",
                        None if preview_image.nsfw_level is None else str(preview_image.nsfw_level),
                    ),
                    ("tagger_backend", backend_id),
                    ("tagger_model", model),
                    ("tagger_threshold", str(settings.threshold)),
                    ("tagger_character_threshold", str(settings.character_threshold)),
                    ("allow_no_credit", candidate.allow_no_credit),
                    ("allow_commercial_use", candidate.allow_commercial_use),
                    ("allow_derivatives", candidate.allow_derivatives),
                    ("allow_different_license", candidate.allow_different_license),
                ),
            )
        )
    return tuple(assets)
