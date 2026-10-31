# KADOKA_PYTHON310_CERTIFI_TLS_SHIM: managed runtime file.

"""Install certifi-backed default TLS contexts for Python 3.10 processes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


# {
#   責務: [install_certifi_default_context: Python 3.10の既定TLS contextをcertifi専用にする]
#   処理: [1: 既存context factoryを保持する, 2: 明示CA指定がないサーバー用contextへcertifi bundleを指定する, 3: sslの既定factoryを差し替える]
#   引数: [ssl_module: 標準ssl module, cafile: certifiが返すCA bundle path]
#   戻り値: []
#   エラー: [ValueError: CA bundle pathが空の場合]
# }
def install_certifi_default_context(ssl_module: Any, cafile: str) -> None:
    if not cafile:
        raise ValueError("certifi CA bundle path is empty")

    original_factory: Callable[..., Any] = ssl_module.create_default_context

    # {
    #   責務: [create_context: 明示CA指定を尊重し既定server contextへcertifi bundleを指定する]
    #   処理: [1: 指定された信頼設定を調べる, 2: 既定server contextだけcertifi bundleを使用する, 3: 元factoryを呼ぶ]
    #   引数: [purpose: TLS contextの用途, cafile: 明示CA bundle, capath: 明示CA directory, cadata: 明示CA data]
    #   戻り値: [context: 元factoryが作成したSSL context]
    # }
    def create_context(
        purpose: Any = ssl_module.Purpose.SERVER_AUTH,
        *,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> Any:
        # Use the refreshed bundle only for implicit server trust; preserve explicit caller policy.
        if (
            purpose == ssl_module.Purpose.SERVER_AUTH
            and cafile is None
            and capath is None
            and cadata is None
        ):
            cafile = certifi_bundle
        return original_factory(
            purpose,
            cafile=cafile,
            capath=capath,
            cadata=cadata,
        )

    certifi_bundle = cafile
    ssl_module.create_default_context = create_context
    ssl_module._create_default_https_context = create_context
