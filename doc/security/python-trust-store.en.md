# Python certificate trust-store audit

[日本語](python-trust-store.md)

## Runtime requirements

The repository CI and development Python use pip 26.2.2 or newer and certifi 2026.10.19 or newer. The pip wheel is upgraded from the official distribution pinned by SHA-256. `tools/security/check_python_ca.py` inspects the pip-bundled bundle, the certifi bundle, and the default SSL trust store actually used by Python. A default store containing an affected certificate does not pass.

On Linux/macOS development environments, select the updated certifi bundle for default TLS:

```bash
source .venv/bin/activate
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
python --version
python -m pip --version
python -c "import certifi; print(certifi.__version__); print(certifi.where())"
python tools/security/check_python_ca.py
```

The Windows build batch and GitHub Actions set the same certifi bundle in `SSL_CERT_FILE` before auditing the trust store. This preserves TLS verification and prevents implicit fallback to a stale OS store. The application's HTTPS requests also use the certifi-only context in `src/comfyui_support_tools/shared/python_tls.py`.

## Audit results (2026-11-02)

| Environment | Python | pip | certifi | Result |
| --- | --- | --- | --- | --- |
| Managed base runtime | 3.12.14 | 26.2.1 | 2026.10.23 | Failed. The pip bundle contained emSign ECC Root CA - G3, and the default OS trust store contained emSign ECC Root CA - G3 and AAA Certificate Services. |
| Repository `.venv` | 3.12.14 | 26.2.2 | 2026.10.23 | Passed. The pip bundle, certifi bundle, and default SSL store selected through `SSL_CERT_FILE` contained none of the affected fingerprints. |

No virtual environments were found under `/workspace` before setup, and no distribution `build/` or `dist/` artifacts were present. The updated `.venv` installs certifi locally so it does not inherit affected roots from the default OS store. Local bundle inspection confirmed the affected emSign/AAA root and intermediate fingerprints are absent. This verifies that these trust stores reject chains terminating in those certificates; it is not a live TLS connection to an external host.

The repository does not use uv or sigstore. uv 0.12.23 was present in the cloud runtime but is unused. The Python sigstore package was not installed. GitHub Artifact Attestations use GitHub's official Actions and `gh attestation`, without a Python sigstore dependency.

The GitHub Releases audit on 2026-11-02 found no existing distribution assets. The Windows onedir workflow is configured to clean-build with the updated dependencies and check the frozen `cacert.pem` and the runner's default trust store. The Windows-specific result is confirmed when the workflow runs.
