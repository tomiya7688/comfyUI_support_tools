# Pinning the CA bundle for Python 3.10 standard TLS

[日本語](python310-stdlib-tls.md)

The Windows build of Python 3.10 can load roots from the Windows certificate store when creating its default SSL context. Setting `SSL_CERT_FILE` alone may therefore leave roots outside the refreshed certifi bundle trusted.

This repository's small shim pins default server-auth TLS contexts in CPython 3.10 to certifi. It also covers `urllib`'s default context and fails closed if certifi cannot be loaded. Explicit CA file, path, or data supplied by a caller remains in effect.

## Install

Run the installer with each target virtual environment's Python:

```powershell
<target venv python.exe> <repository path>\tools\security\install_python310_tls_shim.py
```

The installer only works with a CPython 3.10 virtual environment. It will not overwrite an unmanaged `sitecustomize.py` or `python310_tls_shim.py`. Files are installed into the target interpreter's `site-packages` directory.

## Verify and remove

In a new Python process, verify that the incident canary fails with `CERTIFICATE_VERIFY_FAILED`. Verify a normal public HTTPS endpoint separately.

To remove the shim:

```powershell
<target venv python.exe> <repository path>\tools\security\install_python310_tls_shim.py --remove
```

## Scope

The shim protects code that uses `ssl.create_default_context()` or `urllib`'s default HTTPS context. Applications that read the Windows certificate store directly, or manually create `SSLContext` instances and call `load_default_certs()`, need separate changes. Verify each third-party application's TLS paths after applying the shim.
