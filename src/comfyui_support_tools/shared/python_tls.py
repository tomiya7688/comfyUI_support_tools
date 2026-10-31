"""Create TLS contexts using the managed certifi trust bundle."""

from __future__ import annotations

import ssl

import certifi


# {
#   責務: [create_certifi_context: 管理対象certifi bundleだけを信頼するTLS contextを作成する]
#   処理: [1: certifi CA bundleの場所を取得する, 2: そのbundleから検証用SSL contextを作成する]
#   引数: []
#   戻り値: [context: certifi CA bundleに限定したSSLContext]
# }
def create_certifi_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())
