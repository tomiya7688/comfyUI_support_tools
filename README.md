# comfyUI_support_tools

[日本語](#日本語) | [English](#english)

## 日本語

ComfyUI と関連するローカル画像生成ワークフローを支援するためのツール群です。

### ドキュメント

- [ドキュメント索引 / Documentation index](doc/README.md)
- [コーディング規約（日本語）](doc/コーディング規約.md)
- [Coding Standards (English)](doc/coding-standards.md)
- [共同開発ワークフロー](doc/ワークフロー/ワークフロー.md) / [Development workflow](doc/ワークフロー/workflow.md)

README とプロジェクト管理下のドキュメントは、日本語・英語の両方を維持します。
新規文書と実質的に変更する文書は、同じ変更内で両言語を更新します。

### ライセンス

このリポジトリのプロジェクト所有コードは MIT License で提供されます。
詳細は [LICENSE](LICENSE) を参照してください。

サードパーティ製ライブラリ、バイナリ、モデルウェイト等はこのライセンス表記によって再ライセンスされず、それぞれのライセンスおよび再配布条件に従います。
配布物に含まれるサードパーティ項目は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) で管理していますが、現時点では onedir 成果物に含まれる全ファイルの完全な監査を意味しません。

### AI画像クラスタ

`AI画像クラスタ` タブで画像フォルダーを解析し、`ai_generated` / `non_ai` / `uncertain` の3グループへプレビューできます。Pixiv JSON metadataと埋込生成metadataを先に利用し、明示情報がない画像だけをローカルのOSS判定モデル [`saltacc/anime-ai-detect`](https://huggingface.co/saltacc/anime-ai-detect) で推定します。確認後の出力はコピーのみで、元画像を残し、同名ファイルを上書きしません。必要ならプレビュー表から個別に区分を修正できます。

判定器を使うにはGUIのPython環境に `requirements-ai-image-clustering.txt` と対応するPyTorchを導入します。初回推論ではモデルウェイトがHugging Faceからダウンロードされ、既定では `user_data/cache/ai_origin` に保存されます。モデルはアニメ画像向けで、閾値は未校正です。画像だけのAI判定を確定的な証明として扱わず、迷う結果は `uncertain` に残してください。画像データは外部へ送信しません。モデルウェイトはApache-2.0ライセンスで、アプリへ同梱しません。

現在のPyInstaller onedir版にはPyTorch/Transformersを同梱していないため、凍結実行ファイルではOSSモデルによる推論を利用できません。明示metadataの分類とコピーは使えますが、モデル判定が必要な画像は `uncertain` に残ります。OSSモデル推論を使う場合は、対応依存を導入したソース版GUIを起動してください。

### Pixel Art Creator

`python -m comfyui_support_tools.applications.pixel_art` で独立したPixel Art Creator画面を起動し、Text / Image / Retouchを選べます。`comfyui_support_tools.shared.pixel_art.PixelArtApplication` は3入口で共通設定と処理を使います。8/16/32/64/96/128/192/256 pxとcustom WxH、palette import/extract/export、透明RGBA、crop/pad、palette制限、dither、nearest-neighbor preview、native-sizeのpixel指標、PNG/JSON出力、undo/redo可能なproject履歴、sprite-sheet分割/結合を提供します。text生成は差し替え可能な `PixelTextBackend` が必要で、この起動コマンドにはComfyUIの生成backendをまだ接続していません。

pixel指標は色数・孤立pixel・色補間らしいpixel・輪郭候補等の決定的なheuristicです。semantic readability、カテゴリ適合、outline品質を機械判定したとは扱わず、小サイズはnative previewで確認してください。画像変換は構図を保つcrop/fitと決定的なpalette処理を行いますが、subject segmentationや生成モデルによるsemantic reconstructionは外部backendの拡張点です。現時点ではこのshared application coreであり、統一GUIへの画面接続は含みません。

---

## English

A collection of support tools for ComfyUI and related local image-generation workflows.

### Documentation

- [Documentation index / ドキュメント索引](doc/README.md)
- [Coding Standards (English)](doc/coding-standards.md)
- [コーディング規約（日本語）](doc/コーディング規約.md)
- [Development workflow](doc/ワークフロー/workflow.md) / [共同開発ワークフロー](doc/ワークフロー/ワークフロー.md)

The README and project-owned documentation are maintained in both Japanese and English.
New documents and documents that are substantively modified must update both languages in the same change.

### License

Project-owned code in this repository is licensed under the MIT License.
See [LICENSE](LICENSE).

Third-party libraries, binaries, model weights, and other external materials are not relicensed by this notice and remain subject to their own licenses and redistribution conditions.
A distribution-specific third-party inventory is tracked in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); it is not yet a complete audit of every file in the onedir artifact.

### AI image clustering

The `AI画像クラスタ` tab analyzes an image folder and previews three groups: `ai_generated`, `non_ai`, and `uncertain`. It checks Pixiv JSON metadata and embedded generation metadata first, then uses the local OSS model [`saltacc/anime-ai-detect`](https://huggingface.co/saltacc/anime-ai-detect) only when explicit metadata is absent. After review, images can be copied into the groups; originals are retained and existing files are never overwritten. Individual rows can be manually reassigned.

To use the detector, install `requirements-ai-image-clustering.txt` and a compatible PyTorch build into the GUI's Python environment. The model weights are downloaded from Hugging Face on first inference and stored under `user_data/cache/ai_origin` by default. The model targets anime images and its score thresholds are uncalibrated. Treat image-only results as estimates and keep ambiguous results in `uncertain`. Images are not sent to an external service. The model weights are Apache-2.0 licensed and are not bundled with the application.

The current PyInstaller onedir build does not bundle PyTorch or Transformers, so OSS model inference is unavailable in the frozen executable. Explicit metadata classification and copying still work, while images requiring model inference remain `uncertain`. To use OSS model inference, launch the source version of the GUI with the supported dependencies installed.

### Pixel Art Creator

Launch the standalone Pixel Art Creator window with `python -m comfyui_support_tools.applications.pixel_art` and select Text / Image / Retouch. `comfyui_support_tools.shared.pixel_art.PixelArtApplication` shares processing across these three entry workflows. It provides 8/16/32/64/96/128/192/256 px presets and custom WxH, palette import/extraction/export, transparent RGBA, crop/pad, palette limits, dithering, nearest-neighbor previews, deterministic native-size metrics, PNG/JSON export, undo/redo project history, and basic sprite-sheet split/pack. Text generation requires an injectable `PixelTextBackend`; the launch command does not yet connect a ComfyUI generation backend.

Pixel metrics are deterministic heuristics for color count, isolated pixels, likely interpolated colors, and outline candidates. They do not claim semantic readability, category suitability, or objectively judge outline quality; inspect the native-size preview, especially at small sizes. Image conversion applies composition-aware crop/fit and deterministic palette processing, while subject segmentation and model-assisted semantic reconstruction remain backend extension points. This change supplies the shared application core; it does not connect a GUI screen.
