"""A1111 API adapter for generation model and option catalogs."""

from __future__ import annotations


from .generation_backend_catalog import ChoiceMap, RequestGet


# {
# 責務: [A1111BackendCatalog: AUTOMATIC1111 APIから生成UI用モデル選択肢を集める]
# フィールド: []
# 処理: [1: API応答をcheckpoint・LoRA・VAE・sampler等の選択肢へ変換する]
# }
class A1111BackendCatalog:
    """Query model, upscaler, and sampler names from the A1111 API."""

    _ENDPOINTS = (
        ("checkpoints", "sd-models", ("title", "model_name", "filename")),
        ("loras", "loras", ("name",)),
        ("vaes", "sd-vae", ("model_name", "filename", "name")),
        ("upscalers", "upscalers", ("name",)),
        ("samplers", "samplers", ("name",)),
    )

    # {
    # 責務: [query_choices: AUTOMATIC1111 APIの選択肢をまとめて取得する]
    # 処理: [1: APIの基底URLを正規化する, 2: 選択肢endpointを照会する, 3: 結果と警告を返す]
    # 引数: [base_url: AUTOMATIC1111 APIのURL, request_get: HTTP GET関数]
    # 戻り値: [カテゴリ別選択肢と取得時の警告]
    # }
    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        normalized_url = base_url.strip().rstrip("/")
        if "/sdapi/" in normalized_url:
            normalized_url = normalized_url.split("/sdapi/", 1)[0]
        choices: ChoiceMap = {"checkpoints": [], "unets": [], "loras": [], "vaes": [], "upscalers": [], "samplers": []}
        warnings = []
        for key, endpoint, fields in self._ENDPOINTS:
            try:
                response = request_get(f"{normalized_url}/sdapi/v1/{endpoint}", timeout=5)
                response.raise_for_status()
                for item in response.json():
                    if not isinstance(item, dict):
                        continue
                    value = next((item.get(field) for field in fields if item.get(field)), None)
                    if value:
                        choices[key].append(str(value))
            except Exception as error:
                warnings.append(f"{endpoint}: {error}")
        return choices, warnings
