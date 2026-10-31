# KADOKA_PYTHON310_CERTIFI_TLS_SHIM: managed runtime file.

"""Apply the Python 3.10 certifi TLS shim when this file is installed in a venv."""

from __future__ import annotations

import sys

if sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 10):
    import ssl

    try:
        import certifi
        from python310_tls_shim import install_certifi_default_context

        install_certifi_default_context(ssl, certifi.where())
    except Exception as exc:
        reason = (
            f"Python 3.10 TLS blocked: certifi trust could not be loaded ({type(exc).__name__})"
        )

        # {
        #   責務: [block_default_tls: shimまたはcertifiの欠落時に既定TLSを閉じる]
        #   処理: [1: TLS設定不能の理由をSSL errorとして送出する]
        #   引数: [args: SSL context factoryの位置引数, kwargs: SSL context factoryの名前付き引数]
        #   戻り値: []
        # }
        def block_default_tls(*args, **kwargs):
            raise ssl.SSLError(reason)

        ssl.create_default_context = block_default_tls
        ssl._create_default_https_context = block_default_tls
