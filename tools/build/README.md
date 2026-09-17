# PyInstaller one-dir build

Kadoka Tools を Windows 向け PyInstaller `onedir` 配布物として作成する。
ComfyUI / WebUI1111 / PixAI Tagger 本体やモデルは同梱せず、既存の外部インストール先または HTTP API を利用する。

## Windows: 1 バッチでビルド

リポジトリのルートから次を実行する。

```bat
tools\build\build_onedir.bat
```

バッチは GUI の実行依存と PyInstaller をインストールし、`onedir` ビルド後に凍結済み exe の import smoke test まで実行する。
成功すると次が生成される。

```text
dist\KadokaTools\
  KadokaTools.exe
  ...依存 DLL / Python runtime...
  user_data\input\config\common\
```

`dist\KadokaTools\` ディレクトリ全体を配布単位とする。`KadokaTools.exe` だけを単独で移動しないこと。

## 手動ビルド

```powershell
python -m pip install -r requirements-kadoka-tools.txt
python -m pip install -r tools/build/requirements.txt
python tools/build/build_one_dir.py --smoke-test
```

PyInstaller 6 の `--contents-directory .` を使用している。これにより既存コードの `Path(__file__)` 基準パスが onedir 配布ディレクトリを基準に解決され、`user_data` や外部バックエンドの相対配置を通常実行時と揃える。

## Smoke test

ビルド後の import 検証だけを再実行する場合:

```powershell
dist\KadokaTools\KadokaTools.exe --smoke-test
```

GUI を開かず、`scripts.app` と各タブの import が完了すれば終了コード 0 で終了する。

## 既知の制約

- 配布物に ComfyUI / WebUI1111 / Tagger / モデルは含めない。
- `torch` / `torchvision` / `torchaudio` は意図的に PyInstaller 対象外。重量級処理は各バックエンド側の環境を利用する。
- ffmpeg、7-Zip、外部 downloader 等を使う機能は、それぞれの実行ファイルまたは設定済みパスが必要。
- `user_data` の設定・入力・出力は配布ディレクトリ側に保持する。
- GitHub Actions の `PyInstaller onedir` workflow が Windows で実ビルドと smoke test を行い、成功時は onedir 一式を artifact として保存する。
