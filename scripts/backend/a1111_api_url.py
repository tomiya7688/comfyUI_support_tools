"""Normalize A1111 API URLs before adding endpoint paths."""

from __future__ import annotations

# A1111の既知endpoint形式をrootへ戻すためのsuffix一覧
_A1111_ENDPOINT_SUFFIXES = (
    "/sdapi/v1/txt2img",
    "/sdapi/v1/img2img",
    "/sdapi/v1/interrogate",
    "/sdapi/v1",
    "/sdapi",
)


# {
#   責務: [normalize_a1111_api_root: A1111 API URLから共通rootを取り出す]
#   処理: [1: 前後の空白と末尾slashを正規化する, 2: 既知のAPI endpoint suffixを除去する, 3: endpointを含まないrootを返す]
#   引数: [api_url: 設定されたA1111 API base URLまたはendpoint URL]
#   戻り値: [str: 末尾slashと既知endpointを含まないAPI root]
# }
def normalize_a1111_api_root(api_url: str) -> str:
    root = api_url.strip().rstrip("/")
    for suffix in _A1111_ENDPOINT_SUFFIXES:
        if root.endswith(suffix):
            return root[: -len(suffix)]
    return root
