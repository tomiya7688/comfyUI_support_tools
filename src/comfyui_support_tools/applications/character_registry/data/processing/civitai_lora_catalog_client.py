"""Anonymous metadata-only client for Civitai's public REST API."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)
from src.comfyui_support_tools.shared.contracts.civitai_preview_image import CivitaiPreviewImage

_API_ROOT = "https://civitai.com/api/v1"
_REQUEST_TIMEOUT_SECONDS = 15
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_MAX_QUERY_LENGTH = 200
_MAX_CURSOR_LENGTH = 2048
_MAX_PREVIEW_IMAGES = 100
_ALLOWED_PREVIEW_HOSTS = {"image.civitai.com", "imagecache.civitai.com"}


# {
#   責務: [_preview_images: version responseから安全なCivitai画像参照を抽出する]
#   処理: [画像数とID/URL/閲覧levelを検証し, HTTPSのcivitai.com配下だけを保持する]
#   引数: [payload: model-version API response]
#   戻り値: [tuple[CivitaiPreviewImage, ...]: image bytesを含まない参照一覧]
#   エラー: [RuntimeError: image schema, ID,閲覧level, URLまたは個数が不正な場合]
# }
def _preview_images(payload: dict[str, object]) -> tuple[CivitaiPreviewImage, ...]:
    value = payload.get("images", [])
    if not isinstance(value, list) or len(value) > _MAX_PREVIEW_IMAGES:
        raise RuntimeError("Civitai API images fieldは100件以下の配列である必要があります")
    images: list[CivitaiPreviewImage] = []
    seen_ids: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError("Civitai API image entryがobjectではありません")
        image_id = _required_positive_integer(item, "id")
        image_url = _required_text(item, "url")
        parsed_url = urlsplit(image_url)
        hostname = (parsed_url.hostname or "").casefold()
        if (
            parsed_url.scheme != "https"
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.netloc.casefold() != hostname
            or hostname not in _ALLOWED_PREVIEW_HOSTS
            or parsed_url.fragment
        ):
            raise RuntimeError(
                "Civitai API image URLはcivitai.com配下のHTTPS URLである必要があります"
            )
        nsfw_level = item.get("nsfwLevel")
        if nsfw_level is not None and (
            isinstance(nsfw_level, bool) or not isinstance(nsfw_level, int) or nsfw_level < 0
        ):
            raise RuntimeError("Civitai API image nsfwLevelが不正です")
        if image_id in seen_ids:
            continue
        seen_ids.add(image_id)
        images.append(CivitaiPreviewImage(image_id, image_url, nsfw_level))
    return tuple(images)


# {
#   責務: [_read_json: Civitai public APIからJSON objectを1件取得する]
#   処理: [固定hostへtimeout付きGETを送り, HTTP/network/JSON errorsを利用者向けRuntimeErrorへ変換する]
#   引数: [url: Civitai API URL]
#   戻り値: [dict[str, object]: decoded JSON object]
#   エラー: [RuntimeError: HTTP, connection, timeout, JSON形式またはresponse rootが不正な場合]
# }
def _read_json(url: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "comfyUI-support-tools/1.0",
        },
    )
    try:
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Civitai APIがHTTP {error.code}を返しました") from error
    except (TimeoutError, URLError, OSError) as error:
        raise RuntimeError(f"Civitai APIへの接続に失敗しました: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Civitai APIが不正なJSONを返しました") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Civitai API response rootはJSON objectである必要があります")
    return payload


# {
#   責務: [_required_positive_integer: API payloadの正の整数IDを検証する]
#   処理: [boolを除く正のintだけを返す]
#   引数: [payload: API field mapping, field: 検証field名]
#   戻り値: [int: 検証済みID]
#   エラー: [RuntimeError: fieldが正の整数でない場合]
# }
def _required_positive_integer(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError(f"Civitai API field {field}は正の整数ではありません")
    return value


# {
#   責務: [_required_text: API payloadの必須文字列fieldを検証する]
#   処理: [空白だけでないstrをtrimして返す]
#   引数: [payload: API field mapping, field: 検証field名]
#   戻り値: [str: 検証済みfield]
#   エラー: [RuntimeError: fieldが空または文字列でない場合]
# }
def _required_text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Civitai API field {field}は空でない文字列ではありません")
    return value.strip()


# {
#   責務: [_optional_permission: APIのpermission fieldをbool/string/unknownとして保持する]
#   処理: [None, bool, strのみ受け入れ, stringは空白をtrimする]
#   引数: [payload: API field mapping, field: permission field名]
#   戻り値: [bool | str | None: APIが返した利用条件]
#   エラー: [RuntimeError: 利用条件fieldの型が想定外の場合]
# }
def _optional_permission(payload: dict[str, object], field: str) -> bool | str | None:
    value = payload.get(field)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() or None
    raise RuntimeError(f"Civitai API permission field {field}の型が不正です")


# {
#   責務: [_optional_boolean: APIのnullable boolean fieldを検証する]
#   処理: [Noneまたはboolを返す]
#   引数: [payload: API field mapping, field: boolean field名]
#   戻り値: [bool | None: APIが返した値]
#   エラー: [RuntimeError: fieldがboolまたはnullでない場合]
# }
def _optional_boolean(payload: dict[str, object], field: str) -> bool | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise RuntimeError(f"Civitai API field {field}はbooleanではありません")
    return value


# {
#   責務: [_string_tuple: APIの文字列配列fieldをtupleに変換する]
#   処理: [list[str]のみ検証し, 前後空白と空要素を除いてtuple化する]
#   引数: [payload: API field mapping, field: 配列field名]
#   戻り値: [tuple[str, ...]: 検証済み文字列]
#   エラー: [RuntimeError: 配列または要素の型が不正な場合]
# }
def _string_tuple(payload: dict[str, object], field: str) -> tuple[str, ...]:
    value = payload.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Civitai API field {field}は文字列配列ではありません")
    return tuple(item.strip() for item in value if item.strip())


# {
#   責務: [_trained_words: Civitai trainedWordsをタグtupleと原文へ変換する]
#   処理: [comma区切り文字列はtrimして分割し, listは従来どおり検証する]
#   引数: [payload: Civitai version response]
#   戻り値: [tuple[tuple[str, ...], str | None]: trigger tagと元文字列]
#   エラー: [RuntimeError: trainedWordsの型またはlist要素が不正な場合]
# }
def _trained_words(payload: dict[str, object]) -> tuple[tuple[str, ...], str | None]:
    """Normalize Civitai trainedWords while preserving string-form provenance."""
    value = payload.get("trainedWords", [])
    if isinstance(value, str):
        tags = tuple(tag.strip() for tag in value.split(",") if tag.strip())
        return tags, value
    return _string_tuple(payload, "trainedWords"), None


# {
#   責務: [_candidate_from_model_version: modelとversion summaryからLoRA候補を作る]
#   処理: [LoRA種別, IDs, 作者, base model, tags, 利用条件とsource URLを検証してdomain contractへ写す]
#   引数: [model: Civitai model response, version: modelVersions entry]
#   戻り値: [CivitaiLoraCandidate: 選択できるLoRA version候補]
#   エラー: [RuntimeError: 必須情報または利用条件が不正な場合]
# }
def _candidate_from_model_version(
    model: dict[str, object], version: dict[str, object]
) -> CivitaiLoraCandidate:
    if model.get("type") != "LORA":
        raise RuntimeError("Civitai APIがLoRA以外のmodelを返しました")
    model_id = _required_positive_integer(model, "id")
    version_id = _required_positive_integer(version, "id")
    model_name = _required_text(model, "name")
    version_name = _required_text(version, "name")
    creator_payload = model.get("creator")
    if not isinstance(creator_payload, dict):
        raise RuntimeError("Civitai API creator fieldが不正です")
    creator = _required_text(creator_payload, "username")
    base_model = _required_text(version, "baseModel")
    model_mode = model.get("mode")
    if model_mode is not None and not isinstance(model_mode, str):
        raise RuntimeError("Civitai API model mode fieldが不正です")
    allow_commercial_use = _optional_permission(model, "allowCommercialUse")
    if allow_commercial_use is not None and not isinstance(allow_commercial_use, str):
        raise RuntimeError("Civitai API allowCommercialUse fieldが不正です")
    return CivitaiLoraCandidate(
        model_id=model_id,
        version_id=version_id,
        model_name=model_name,
        version_name=version_name,
        creator=creator,
        base_model=base_model,
        tags=_string_tuple(model, "tags"),
        source_url=f"https://civitai.com/models/{model_id}?modelVersionId={version_id}",
        allow_no_credit=_optional_boolean(model, "allowNoCredit"),
        allow_commercial_use=allow_commercial_use,
        allow_derivatives=_optional_boolean(model, "allowDerivatives"),
        allow_different_license=_optional_boolean(model, "allowDifferentLicense"),
        model_mode=model_mode,
    )


# {
#   責務: [search_civitai_loras: Civitai public APIからLoRA検索結果1ページを取得する]
#   処理: [query/limit/cursorを検証, types=LORAで検索し, model version別候補とnextCursorを返す]
#   引数: [query: 検索語, limit: 1〜100件のページサイズ, cursor: APIが返したopaque cursor]
#   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: version候補と次ページcursor]
#   エラー: [ValueError: 入力が不正, RuntimeError: API通信またはresponse schemaが不正]
# }
def search_civitai_loras(
    query: str,
    limit: int = _DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
    if not isinstance(query, str) or not query.strip() or len(query) > _MAX_QUERY_LENGTH:
        raise ValueError(f"queryは1〜{_MAX_QUERY_LENGTH}文字で指定してください")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_PAGE_SIZE:
        raise ValueError(f"limitは1〜{_MAX_PAGE_SIZE}の整数で指定してください")
    if cursor is not None and (
        not isinstance(cursor, str) or not cursor.strip() or len(cursor) > _MAX_CURSOR_LENGTH
    ):
        raise ValueError(f"cursorは1〜{_MAX_CURSOR_LENGTH}文字で指定してください")

    parameters = {"types": "LORA", "query": query.strip(), "limit": str(limit)}
    if cursor is not None:
        parameters["cursor"] = cursor
    payload = _read_json(f"{_API_ROOT}/models?{urlencode(parameters)}")
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Civitai API items fieldが配列ではありません")
    candidates: list[CivitaiLoraCandidate] = []
    for model in items:
        if not isinstance(model, dict):
            raise RuntimeError("Civitai API model entryがobjectではありません")
        versions = model.get("modelVersions")
        if not isinstance(versions, list):
            raise RuntimeError("Civitai API modelVersions fieldが配列ではありません")
        for version in versions:
            if not isinstance(version, dict):
                raise RuntimeError("Civitai API model version entryがobjectではありません")
            candidates.append(_candidate_from_model_version(model, version))

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RuntimeError("Civitai API metadata fieldがobjectではありません")
    next_cursor = metadata.get("nextCursor")
    if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor.strip()):
        raise RuntimeError("Civitai API nextCursor fieldが不正です")
    return tuple(candidates), next_cursor


# {
#   責務: [fetch_civitai_lora_version: 選択したCivitai LoRA versionのtrainedWordsを取得する]
#   処理: [candidate IDでversion endpointを取得し, identityを照合してtrainedWordsを分割し原文を保持する]
#   引数: [candidate: search結果から選択したLoRA version]
#   戻り値: [CivitaiLoraVersionMetadata: trained words, publication status, availability付きmetadata]
#   エラー: [ValueError: candidateが不正, RuntimeError: API通信/schema/ID照合が失敗した場合]
# }
def fetch_civitai_lora_version(
    candidate: CivitaiLoraCandidate,
) -> CivitaiLoraVersionMetadata:
    """Fetch one version's normalized trainedWords and retain string provenance."""
    if not isinstance(candidate, CivitaiLoraCandidate):
        raise ValueError("candidateはCivitaiLoraCandidateで指定してください")
    payload = _read_json(f"{_API_ROOT}/model-versions/{candidate.version_id}")
    if _required_positive_integer(payload, "id") != candidate.version_id:
        raise RuntimeError("Civitai APIが要求したものと異なるversionを返しました")
    if _required_positive_integer(payload, "modelId") != candidate.model_id:
        raise RuntimeError("Civitai API versionがcandidateのmodel IDと一致しません")
    trained_words, raw_trained_words = _trained_words(payload)
    return CivitaiLoraVersionMetadata(
        candidate=candidate,
        trained_words=trained_words,
        status=_required_text(payload, "status"),
        availability=_required_text(payload, "availability"),
        raw_trained_words=raw_trained_words,
        preview_images=_preview_images(payload),
    )
