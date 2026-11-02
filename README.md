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

### Touka候補評価

Toukaの動画候補scoreは、候補生成中のmetricから独立したversion付きevaluatorで計算し、`candidate_scores.json` にscore内訳とevaluator versionを記録します。`calibrate_linear_evaluator` は人手のground-truth品質ラベルからlinear evaluatorをfitし、同じevaluator contractで候補を順位付けできます。ranking検証ユーティリティはpairwise accuracy、top-1選択率、top-k良候補包含率を測定します。リポジトリには代表的な人手ラベルsetがないため既定は既存係数をversion付きbaselineとして使用します。校正・検証するまではscoreを画質の保証として扱わないでください。

### モデル系統判定

Tensor検出器は `ModelFamilyDetectorRegistry` へ登録でき、結果にdetector ID/versionと一致confidenceを保持します。path・metadata・tensor evidenceが衝突した場合や未対応layoutの場合は `unknown` を維持します。追加detectorは既存のtensor detectorを編集せずfixtureから登録できます。

### 生成パラメータ

Random Image の CFG、steps、resolution、sampler は共通 `ParameterSpecRegistry` から解決します。seed、scheduler、独自parameter、backend namespace付き値はspec登録で追加でき、解決済み値は既存4項目との互換形式を保ちながら `parameters` / `backend_parameters` に保存されます。UIとpresetはregistryのschema descriptorを共有できます。

### 出力成果物

共通 `output_artifact` helper は fail / skip / overwrite / rename / versioned conflict policy、入力とのpath衝突防止、一時ファイルへのfsync、commit前validator、atomic publishを提供します。Inspectorのsidecar exportはこのhelperを使ってJSON検証後に書き込みます。

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

### Touka candidate evaluation

Touka video candidate scores are computed by a separate, versioned evaluator from candidate metrics. `candidate_scores.json` records the metric breakdown and evaluator version. `calibrate_linear_evaluator` fits the same evaluator contract from human ground-truth quality labels; the ranking validator measures pairwise accuracy, top-1 selection, and top-k inclusion. The repository has no representative labeled dataset, so the default remains the versioned legacy baseline. Do not treat its score as a quality guarantee until it is calibrated and validated on representative data.

### Model family detection

Tensor detectors register through `ModelFamilyDetectorRegistry`, and classifications retain detector ID/version and match confidence. Conflicting path, metadata, and tensor evidence, as well as unsupported layouts, remain `unknown`. A fixture can register an additional detector without editing the existing tensor detector.

### Generation parameters

Random Image CFG, steps, resolution, and sampler resolve through the shared `ParameterSpecRegistry`. Seed, scheduler, custom parameters, and backend-namespaced values can be added through spec registration. Resolved values preserve the existing four-field representation and store extensions under `parameters` / `backend_parameters`. UI and presets can share the registry schema descriptors.

### Output artifacts

The shared `output_artifact` helper provides fail, skip, overwrite, rename, and versioned conflict policies, source-path collision protection, fsynced temporary writes, validation before commit, and atomic publication. Inspector sidecar export uses it to validate JSON before publishing.
