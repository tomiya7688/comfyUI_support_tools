# Python 3.10標準TLSのCA固定

[English](python310-stdlib-tls.en.md)

Python 3.10のWindows版は標準SSL contextからWindows証明書ストアも利用します。`SSL_CERT_FILE`を設定するだけでは、更新済みcertifi bundleに含まれないルートを拒否できない場合があります。

このリポジトリの小さなshimは、CPython 3.10の既定server-auth TLS contextをcertifi bundleへ固定します。`urllib`の既定contextにも適用し、certifiが読み込めない場合は既定TLSを失敗させます。呼び出し側がCA file/path/dataを明示した場合は、その指定を維持します。

## インストール

各対象venvのPythonで次を実行します。

```powershell
<対象venvのpython.exe> <リポジトリのパス>\tools\security\install_python310_tls_shim.py
```

installerはCPython 3.10のvenv以外では動作せず、既存の管理外 `sitecustomize.py` / `python310_tls_shim.py` を上書きしません。配置先は対象Pythonが返す `site-packages` です。

## 検証と削除

更新されたPython processで、カナリア接続が `CERTIFICATE_VERIFY_FAILED` になることを確認します。通常の公開HTTPSも別途確認してください。

shimを削除する場合:

```powershell
<対象venvのpython.exe> <リポジトリのパス>\tools\security\install_python310_tls_shim.py --remove
```

## 範囲

このshimは `ssl.create_default_context()` と `urllib` の既定HTTPS contextを使うコードを保護します。アプリがWindows証明書ストアを直接読んだり、手動で `SSLContext` を生成して `load_default_certs()` を呼ぶ経路は別途修正が必要です。適用後も第三者アプリの個別TLS経路を検証してください。
