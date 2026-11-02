# Python証明書信頼ストアの確認

[English](python-trust-store.en.md)

## 実行環境

このリポジトリのCIと開発用Pythonでは pip 26.2.2以上、certifi 2026.10.19以上を使用します。pip wheelはSHA-256で固定した公式配布物から更新し、`tools/security/check_python_ca.py` はpip内蔵bundle、certifi bundle、Pythonが実際に使う既定SSL trust storeを検査します。既定trust storeに対象証明書が残っている環境は成功扱いにしません。

Linux/macOSの開発環境では更新済みcertifiを既定TLS trust storeとして明示します:

```bash
source .venv/bin/activate
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
python --version
python -m pip --version
python -c "import certifi; print(certifi.__version__); print(certifi.where())"
python tools/security/check_python_ca.py
```

WindowsビルドバッチとGitHub Actionsは同じcertifi bundleを `SSL_CERT_FILE` に設定してからtrust storeを検査します。これはTLS検証を無効にせず、古いOS storeへ暗黙にフォールバックしない設定です。アプリ内の既定HTTPS要求も `src/comfyui_support_tools/shared/python_tls.py` のcertifi専用contextを使います。

## 監査結果 (2026-11-02)

| 環境 | Python | pip | certifi | 結果 |
| --- | --- | --- | --- | --- |
| マネージドベースruntime | 3.12.14 | 26.2.1 | 2026.10.23 | 不合格。pip bundleにemSign ECC Root CA - G3が残る。`SSL_CERT_FILE` 未設定時の既定SSL storeはCA証明書0件。ランタイム管理下のためこのリポジトリからpipを更新できない。 |
| リポジトリ `.venv` | 3.12.14 | 26.2.2 | 2026.10.23 | 合格。pip bundle、certifi bundle、`SSL_CERT_FILE` で選択した既定SSL storeのいずれにも対象fingerprintがない。`SSL_CERT_FILE` を外すと既定storeはCA証明書0件となるため検査は失敗する。 |
| `/workspace/comfy-tools-venv` | 3.12.14 | 26.2.2 | 2026.10.23 | 旧pip 25.0.1から公式SHA-256固定wheelで更新後に合格。pip/certifi bundleと選択中SSL storeに対象fingerprintがない。 |

監査では `/workspace` 内の2つのvenvを確認しました。両方のpipをPython.orgのSHA-256固定pip 26.2.2 wheelで更新し、各環境で再検査しました。更新済みvenvは `SSL_CERT_FILE` に各環境のcertifi bundleを指定して検査します。各CA bundle内の対象emSign/AAA rootおよび中間証明書fingerprintが不在であることを確認しました。これは選択されたtrust storeが対象証明書を信頼しないことの検査で、外部ホストへのTLS接続試験ではありません。マネージドベースruntimeは `/opt` 配下にあり、workspace外のpipをこの作業から変更できないため pip 26.2.1 のままです。

リポジトリ内にuvやsigstoreの利用箇所はありません。uv 0.12.23はcloud runtimeにありましたが未使用です。sigstore Python packageはruntimeにありません。GitHub Artifact AttestationsはGitHub Actionsの公式actionと`gh attestation`を使い、Python sigstore packageには依存しません。

2026-11-02のGitHub Release調査では既存配布assetはありませんでした。Windows onedir workflowは修正済み依存でクリーンbuildし、凍結成果物の `cacert.pem` とrunnerが使う既定trust storeをCIで検証する設定です。実Windows runner上の結果はそのworkflow実行時に確認されます。
