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
- GitHub Actions の `PyInstaller onedir` workflow は PR/main push で build/smoke test を行う。署名用 secrets を使う配布はタグを選んで workflow を手動実行し、Authenticode と GitHub attestation の検証後にのみ Release を作成・公開する。

## 公開配布の署名と検証

GitHub Actions の `PyInstaller onedir` workflow は PR とmain pushでビルドと smoke test のみを行い、未署名 artifact を upload しない。タグを指定した workflow 手動実行では、required reviewers とタグ限定 deployment rule を設定した `windows-release-signing` GitHub Environment を使い、`WINDOWS_CODESIGN_PFX_BASE64` / `WINDOWS_CODESIGN_PFX_PASSWORD` を environment secrets として登録する。全 PE を Authenticode SHA-256 + RFC 3161 timestamp で署名・検証し、`tools/build/package_artifact.py` が onedir 全体を deterministic ZIP にまとめ、`SHA256SUMS.txt` を作成・照合する。ZIPを展開して最終成果物中の全PE署名と同一publisherを再検証してから、GitHub Artifact Attestations を ZIP と checksum manifest の双方へ付ける。`gh attestation verify` 成功後にのみ最終artifactを保存し、その後にRelease assetsを公開する。PR と main のCIは秘密情報を持たない `ci` environment を使う。署名鍵はrepositoryへ保存しない。secrets が未設定・署名不可の場合は公開artifact作成を失敗させる。

ユーザーはReleaseから `KadokaTools-windows-onedir.zip` と `SHA256SUMS.txt` を取得し、README記載の `gh attestation verify`、SHA-256照合、展開後のAuthenticode検証を行う。2026-11-02の調査時点ではGitHub Releaseが公開されていないため、修復対象の既存配布Releaseはなかった。現在の配布物一覧は Windows onedir ZIP とその checksum manifest のみ。

## Public artifact signing and verification

The `PyInstaller onedir` GitHub Actions workflow builds and smoke-tests pull requests and main-branch pushes without uploading unsigned artifacts. Configure the `windows-release-signing` GitHub Environment with required reviewers and tag-only deployment rules, and store `WINDOWS_CODESIGN_PFX_BASE64` / `WINDOWS_CODESIGN_PFX_PASSWORD` there as environment secrets. Manual tag runs Authenticode-sign all PE files with SHA-256 and an RFC 3161 timestamp, package the complete onedir tree as a deterministic ZIP, and write/verify `SHA256SUMS.txt`. The workflow extracts the final ZIP and verifies every PE signature and common publisher, then attaches GitHub Artifact Attestations to both files and publishes only after `gh attestation verify` succeeds. Pull requests and main-branch builds use a secret-free `ci` environment. The signing key is never stored in the repository. Missing credentials or failed signing blocks publication.

Users download `KadokaTools-windows-onedir.zip` and `SHA256SUMS.txt` from a Release, then follow the README commands to verify attestations, the ZIP digest, and Authenticode after extraction. No GitHub Releases were published at the 2026-11-02 audit, so there were no historical release assets to remediate. The current artifact inventory consists only of the Windows onedir ZIP and its checksum manifest.
