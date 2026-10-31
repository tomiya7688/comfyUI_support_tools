# KADOKA_PYTHON310_CERTIFI_TLS_SHIM: managed runtime file.

"""Apply the Python 3.10 certifi TLS shim when this file is installed in a venv."""

from __future__ import annotations

import sys

if sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 10):
    import ssl

    original_factory = ssl.create_default_context
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
        #   処理: [1: 暗黙のserver trustを拒否する, 2: 呼出元が明示したCA設定は元factoryへ渡す]
        #   引数: [purpose: TLS contextの用途, cafile: CA bundle, capath: CA directory, cadata: CA data]
        #   戻り値: []
        # }
        def block_default_tls(
            purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None
        ):
            if purpose == ssl.Purpose.SERVER_AUTH and not (cafile or capath or cadata):
                raise ssl.SSLError(reason)
            return original_factory(
                purpose,
                cafile=cafile,
                capath=capath,
                cadata=cadata,
            )

        ssl.create_default_context = block_default_tls
        ssl._create_default_https_context = block_default_tls
        for module in tuple(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            if namespace is None or namespace is globals():
                continue
            for name, value in tuple(namespace.items()):
                if value is original_factory:
                    namespace[name] = block_default_tls
