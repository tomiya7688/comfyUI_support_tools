# comfyUI_support_tools

[日本語](#日本語) | [English](#english)

## 日本語

ComfyUI と関連するローカル画像生成ワークフローを支援するためのツール群です。

### ドキュメント

- [ドキュメント索引 / Documentation index](doc/README.md)
- [コーディング規約（日本語）](doc/コーディング規約.md)
- [Coding Standards (English)](doc/coding-standards.md)
- [共同開発ワークフロー](doc/ワークフロー/ワークフロー.md) / [Development workflow](doc/ワークフロー/workflow.md)

PR前の標準ローカル検査は `python tools/completion/check.py` です。差分に応じたsyntax/quality/tests/docs検査を一括実行します。

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

### Windows配布物の真正性検証

配布単位は Authenticode 署名済み Windows `onedir` を格納する `KadokaTools-windows-onedir.zip` と `SHA256SUMS.txt` です。タグを指定して GitHub Actions workflow を手動実行すると、公開配布前に全 PE ファイルを RFC 3161 timestamp 付きで署名・検証し、最終 ZIP 展開後にも署名と publisher の一致を検証します。最終 ZIP と checksum manifest の両方へ GitHub Artifact Attestation を付け、attestation 検証後に Release assets を公開します。`windows-release-signing` GitHub Environment に required reviewers とタグ限定ルールを設定し、署名用 secrets をその environment のみへ登録してください。PR と main の CI は秘密情報を持たない `ci` environment を使用します。配布 Release のない既存の状態を確認したため、未署名の過去 Release は見つかりませんでした（監査日: 2026-11-02）。

Release asset をダウンロード後、ZIP と checksum manifest の provenance を確認し、checksum を照合します:

```powershell
gh attestation verify KadokaTools-windows-onedir.zip --repo tomiya7688/comfyUI_support_tools --signer-workflow tomiya7688/comfyUI_support_tools/.github/workflows/pyinstaller-onedir.yml
gh attestation verify SHA256SUMS.txt --repo tomiya7688/comfyUI_support_tools --signer-workflow tomiya7688/comfyUI_support_tools/.github/workflows/pyinstaller-onedir.yml
$expected = ((Get-Content SHA256SUMS.txt -Raw) -split '\s+')[0]
$actual = (Get-FileHash KadokaTools-windows-onedir.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
```

ZIP 展開後、すべての PE binary の Windows 署名を確認できます: `Get-ChildItem .\KadokaTools -Recurse -File | Where-Object { $_.Extension -in @('.exe', '.dll', '.pyd') } | ForEach-Object { if ((Get-AuthenticodeSignature $_).Status -ne 'Valid') { throw 'Authenticode verification failed' } }`。GitHub Actions artifact wrapper を取得した場合は、まず ZIP と `SHA256SUMS.txt` を取り出して検証してください。Release 配布は署名用 repository secrets がない場合 fail-closed となります。

### Touka候補評価

Toukaの動画候補scoreは、候補生成中のmetricから独立したversion付きevaluatorで計算し、`candidate_scores.json` にscore内訳とevaluator versionを記録します。`calibrate_linear_evaluator` は人手のground-truth品質ラベルからlinear evaluatorをfitし、同じevaluator contractで候補を順位付けできます。ranking検証ユーティリティはpairwise accuracy、top-1選択率、top-k良候補包含率を測定します。リポジトリには代表的な人手ラベルsetがないため既定は既存係数をversion付きbaselineとして使用します。校正・検証するまではscoreを画質の保証として扱わないでください。

### モデル系統判定

Tensor検出器は `ModelFamilyDetectorRegistry` へ登録でき、結果にdetector ID/versionと一致confidenceを保持します。path・metadata・tensor evidenceが衝突した場合や未対応layoutの場合は `unknown` を維持します。追加detectorは既存のtensor detectorを編集せずfixtureから登録できます。

### Pixiv Dataset Downloader

`comfyui_support_tools.shared.pixiv_dataset` はPixivPy3 source adapter、refresh-token auth/health、tag・creator・bookmark・ranking・ID query、filter、rate limit/retry、JobRuntime bridge、resume checkpoint、ページ順を維持したillustration/mangaとugoira archive収集、任意GIF/WebP preview、work/provenance JSON、exact/perceptual duplicate grouping、#356 handoffを提供します。`PixivRateLimitProfile`で毎分上限、API/download並列上限、interval、retry/backoff、429 cooldown、自動pauseをapp/query/job単位に設定でき、effective設定とbounded retry/429履歴をcheckpointへ記録します。使う場合は別環境に `pip install -r requirements-pixiv.txt` でPixivPy3を導入し、呼び出し元のsecure secret storeからrefresh tokenを実行時に渡してください。tokenをpresetやdatasetへ保存しません。

このbackendはAPI接続型で、認証情報と実Pixiv応答がない環境では実アカウントへの通信を実行しません。GUIのquery builder/preview controls、CLI command、非original派生画像の取得、動画(MP4)変換は未実装です。権利許可は常に`unknown`として保存され、duplicateはgroup化のみで自動削除しません。詳細は[Pixiv Dataset Downloader](doc/dataset/pixiv_dataset.md)を参照してください。

### Modern Trainer Adapter Registry

`comfyui_support_tools.shared.trainer_registry` はSimpleTuner / AI Toolkit / sd-scriptsを共通`TrainingSpec`からtrainer別JSON/YAML/TOML/CLIへ変換し、SDXL/FLUX.1/FLUX.2/Qwen Image/SD3.5/Anima/Hunyuan/Krea2/HiDreamのarchitecture profile、LoRA/LyCORIS method status、version/capability cache、target module discovery、quantization/offload適合性、provenance、1–8 step smoke gateを提供します。Autoはruntimeでsupportedと確認されたmethodだけを選び、smokeでcheckpointとsampleが得られない場合はfull training callbackを実行しません。trainer実体とmodelを使ったlive validationは未実施です。詳細は[Modern Trainer Adapter Registry](doc/trainer_registry.md)を参照してください。

### LoRA Training Doctor

`comfyui_support_tools.shared.training_doctor` はcharacter/style/object/multi-concept向け固定validation matrix、同一seed/sampler/steps/resolutionのcheckpoint比較、trigger/strength sweep、task別weighted score、leakage/memorization/base-preservation/diversity signal、patience付きearly-stop callback、best checkpoint選択/rollback、training curveとsample preview付きreport保存を提供します。`ValidationEvaluator`は#20品質評価の実測値を受け取り、`publish_prompt_metadata`は#240互換sinkへtrigger/tags/strengthを渡します。trainer/ComfyUI実生成adapterはこの環境にないためlive integrationは未検証です。詳細は[LoRA Training Doctor](doc/training_doctor.md)を参照してください。

### LoRA Dataset Curator / Caption Planner

`python -m comfyui_support_tools.applications.lora_dataset_curator`でGUIを起動し、task-aware caption、Character Registryのtrait/outfit、quality proxy、duplicate group、coverage、validation split、sample weightを確認・手動修正してからSimpleTuner / AI Toolkit / sd-scripts向けdataset treeをexportできます。入力画像・sidecarは変更せず、fingerprintとdecision manifestを保存します。vision taggerとtrainer固有weight adapterは注入式で、実trainerによるtrainingは未検証です。詳細は[LoRA Dataset Curator](doc/lora_dataset_curator.md)を参照してください。

### Composition Template Extractor

`python -m comfyui_support_tools.applications.composition_template`で画像から正規化した構図領域、余白、saliency proxy、任意のhorizonを抽出し、手動trace・role編集・wireframe確認・aspect-ratio adaptation・JSON/library保存・generation guidance exportを行えます。標準抽出は色/identity/styleを含まない低信頼度ヒューリスティックです。pose、semantic segmentation、depth、vanishing-point推定adapterは注入可能ですが標準実装にはなく、#348/#56/#82/#84/#354の実接続も未実装です。評価・使い方は[日本語ガイド](doc/composition_template.md) / [English guide](doc/composition_template.en.md)を参照してください。

### Manga Creator / Storyboard

`python -m comfyui_support_tools.applications.manga_creator`で編集可能なMangaProject、Character/Location/Prop Bible、story→page/panel storyboard、4コマ/通常漫画/webtoon/splash layout、別レイヤーdialogue/balloon、continuity event、best-of-N candidate保存、panel単位再生成、page合成、JSONによる保存/再開を行えます。既定backendはrough storyboard sketchです。`COMFYUI_MANGA_WORKFLOW`にAPI workflow JSONを指定するとComfyUIへ接続できます。汎用workflowには参照画像conditioningは注入されず、MangaFlow/DiffSensei等、#348/#350/#353 router、Job Queue、縦書き対応CJK font、story/identity/OCR評価、局所inpaint repair、PDF/CBZ exportは未接続です。仕様・検証範囲は[Manga Creator](doc/manga_creator.md) / [English guide](doc/manga_creator.en.md)を参照してください。

### Expression Retouch

`python -m comfyui_support_tools.applications.expression_retouch`で顔選択、expression preset、局所maskの手動追加/消去、ComfyUI inpaint workflow、候補比較とsource/mask/history保存を行えます。OpenCV Haarの顔パーツ領域とidentity評価はproxyで、semantic expression evaluatorは注入可能です。ComfyUI workflowとimage/mask node IDsは`EXPRESSION_RETOUCH_*`環境変数で設定します。詳細は[Expression Retouch](doc/expression_retouch.md) / [English guide](doc/expression_retouch.en.md)を参照してください。

### LoRA Composition Lab

`comfyui_support_tools.shared.lora_composition` は互換性preflight、LoRA update norm/cosine/subspace/sign conflict分析、weighted/top-K/Zip-style training-free merge、rank圧縮、global/per-layer scale grid探索、seed固定の評価bridge、user scale preference prior、provenance付きsafetensorsとruntime recipe出力を提供します。任意依存は `pip install -r requirements-lora-composition.txt` で導入します。分析するdense updateは1 layerあたり8,388,608要素に制限します。Zip-style/top-Kは研究論文実装そのものではなく、比較可能なtraining-free baselineです。GUIと画像生成/evaluation adapterの統合は未実装です。詳細は[LoRA Composition Lab](doc/lora_composition.md)を参照してください。

### Image Dataset Classifier / Sorter

`comfyui_support_tools.shared.dataset_classifier.DatasetClassifierApplication` は再帰inventory、axis classifier registry、複数evidenceの重み付きfusion、metadata優先、alternate label/disagreement/uncertain分類、manual review保存、AND/OR/NOT query、style embedding clustering adapter、dry-run/copy/move/manifest-only、collision回避、caption/metadata sidecar検証付き転送を提供します。JSON sidecarのlabelは既定priorityで他model evidenceより優先し、queryは必要なaxisだけを分類できます。結果manifestにはsource/output、labels、confidence、evidence provenance、manual overrideを記録し、#356向けhandoff payloadも作れます。

character/situation/background/styleの学習済みclassifierやembedding modelは同梱せず、adapter未登録のaxisは`uncertain`になります。ローカルJSON metadataと利用者が登録するmodelsを使うshared serviceです。GitHub issue #369の完全なreview GUIと本番semantic model接続は未実装です。

### 生成パラメータ

Random Image の CFG、steps、resolution、sampler は共通 `ParameterSpecRegistry` から解決します。seed、scheduler、独自parameter、backend namespace付き値はspec登録で追加でき、解決済み値は既存4項目との互換形式を保ちながら `parameters` / `backend_parameters` に保存されます。UIとpresetはregistryのschema descriptorを共有できます。

### 出力成果物

共通 `output_artifact` helper は fail / skip / overwrite / rename / versioned conflict policy、入力とのpath衝突防止、一時ファイルへのfsync、commit前validator、atomic publishを提供します。Inspectorのsidecar exportはこのhelperを使ってJSON検証後に書き込みます。

### MMD Model Doctor基盤

`comfyui_support_tools.shared.mmd_doctor` はPMX 2.0/2.1の構造を安全に読み取り、bone hierarchy・weight・morph参照・rigid body・joint・soft bodyの診断と局所修正候補を生成します。修正は元ファイルへ上書きせず、motion evaluatorが注入された場合だけ候補をBest-of-N比較し、選択されたPMXとbefore/after診断・バイト差分を別ファイルへ保存します。外部のMMD物理engineとweight推定器はadapterとして接続できます。

この段階ではPMX 2.1のsoft body、GUI、MMD Bullet motion evaluator、SkinTokens/UniRig等のweight推定modelは同梱していません。soft bodyを含むファイルは不完全な監査を避けるため拒否し、evaluator未設定時は自動選択・自動exportを行いません。

---

## English

A collection of support tools for ComfyUI and related local image-generation workflows.

### Documentation

- [Documentation index / ドキュメント索引](doc/README.md)
- [Coding Standards (English)](doc/coding-standards.md)
- [コーディング規約（日本語）](doc/コーディング規約.md)
- [Development workflow](doc/ワークフロー/workflow.md) / [共同開発ワークフロー](doc/ワークフロー/ワークフロー.md)

Run `python tools/completion/check.py` as the standard pre-PR local check. It selects syntax, quality, tests, and generated-doc checks from the current diff.

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

### Verifying Windows distributions

The final deliverables are `KadokaTools-windows-onedir.zip` (the Authenticode-signed Windows `onedir`) and `SHA256SUMS.txt`. A manual GitHub Actions run targeting a tag signs and verifies every PE file with an RFC 3161 timestamp, then verifies signatures and a common publisher again after extracting the final ZIP. It attaches GitHub Artifact Attestations to both the final ZIP and checksum manifest, verifies those attestations, and only then publishes Release assets. Configure the `windows-release-signing` GitHub Environment with required reviewers and tag-only deployment rules, and store signing secrets only in that environment. Pull requests and main-branch CI use a secret-free `ci` environment. The repository had no published Release assets during the audit, so no unsigned historical Release needed remediation (audit date: 2026-11-02).

After downloading the Release assets, verify provenance for both files and compare the ZIP digest:

```powershell
gh attestation verify KadokaTools-windows-onedir.zip --repo tomiya7688/comfyUI_support_tools --signer-workflow tomiya7688/comfyUI_support_tools/.github/workflows/pyinstaller-onedir.yml
gh attestation verify SHA256SUMS.txt --repo tomiya7688/comfyUI_support_tools --signer-workflow tomiya7688/comfyUI_support_tools/.github/workflows/pyinstaller-onedir.yml
$expected = ((Get-Content SHA256SUMS.txt -Raw) -split '\s+')[0]
$actual = (Get-FileHash KadokaTools-windows-onedir.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'SHA-256 mismatch' }
```

After extracting the ZIP, verify every PE binary signature with `Get-ChildItem .\KadokaTools -Recurse -File | Where-Object { $_.Extension -in @('.exe', '.dll', '.pyd') } | ForEach-Object { if ((Get-AuthenticodeSignature $_).Status -ne 'Valid') { throw 'Authenticode verification failed' } }`. If you download the GitHub Actions artifact wrapper, extract the ZIP and checksum manifest from it before verification. Release publication fails closed until the repository signing secrets are configured.

### Touka candidate evaluation

Touka video candidate scores are computed by a separate, versioned evaluator from candidate metrics. `candidate_scores.json` records the metric breakdown and evaluator version. `calibrate_linear_evaluator` fits the same evaluator contract from human ground-truth quality labels; the ranking validator measures pairwise accuracy, top-1 selection, and top-k inclusion. The repository has no representative labeled dataset, so the default remains the versioned legacy baseline. Do not treat its score as a quality guarantee until it is calibrated and validated on representative data.

### Model family detection

Tensor detectors register through `ModelFamilyDetectorRegistry`, and classifications retain detector ID/version and match confidence. Conflicting path, metadata, and tensor evidence, as well as unsupported layouts, remain `unknown`. A fixture can register an additional detector without editing the existing tensor detector.

### Pixiv Dataset Downloader

`comfyui_support_tools.shared.pixiv_dataset` provides a PixivPy3 adapter, refresh-token authentication and health checks, tag/creator/bookmark/ranking/ID queries, filtering, throttling and bounded retries, JobRuntime integration, resumable checkpoints, ordered illustration/manga pages and ugoira archives, optional GIF/WebP previews, work/provenance JSON, exact/perceptual duplicate grouping, and a #356 handoff. `PixivRateLimitProfile` configures requests/minute, API/download concurrency caps, interval, retries/backoff, 429 cooldown, and automatic pause at application/query/job scope; the effective policy and bounded retry/429 history are recorded in the checkpoint. Install PixivPy3 separately with `pip install -r requirements-pixiv.txt`; supply the refresh token at runtime through the caller's secure secret store. Presets and dataset files never store it.

This backend requires live Pixiv credentials and API responses for account-level validation, which are not available in the offline test suite. The query-builder GUI, CLI command, non-original rendition selection, and MP4 conversion are not implemented. Rights remain `unknown`; duplicate handling groups records and never deletes files. See [Pixiv Dataset Downloader](doc/dataset/pixiv_dataset.md).

### Modern Trainer Adapter Registry

`comfyui_support_tools.shared.trainer_registry` translates a shared `TrainingSpec` into trainer-specific SimpleTuner / AI Toolkit / sd-scripts JSON/YAML/TOML/CLI, and provides SDXL/FLUX.1/FLUX.2/Qwen Image/SD3.5/Anima/Hunyuan/Krea2/HiDream architecture profiles, LoRA/LyCORIS method states, versioned capability cache, target-module discovery, quantization/offload validation, provenance and a 1–8 step smoke gate. Auto selects only methods confirmed as supported at runtime; full-training callbacks do not run unless smoke produces both a checkpoint and sample. Live validation with installed trainers and model weights has not been performed. See [Modern Trainer Adapter Registry](doc/trainer_registry.en.md).

### LoRA Training Doctor

`comfyui_support_tools.shared.training_doctor` provides fixed character/style/object/multi-concept validation matrices, checkpoint comparisons under the same seed/sampler/steps/resolution, trigger and strength sweeps, task-weighted scores, leakage/memorization/base-preservation/diversity signals, patience-based early-stop callbacks, best-checkpoint selection/rollback, and report persistence with training curves and sample previews. `ValidationEvaluator` accepts measured #20 image-quality evidence, and `publish_prompt_metadata` sends trigger/tags/strength to a #240-compatible sink. No live trainer/ComfyUI generation adapter is configured in this environment, so live integration is unverified. See [LoRA Training Doctor](doc/training_doctor.en.md).

### LoRA Dataset Curator / Caption Planner

Launch the GUI with `python -m comfyui_support_tools.applications.lora_dataset_curator` to review and edit task-aware captions, Character Registry traits/outfits, quality proxies, duplicate groups, coverage, validation splits, and sample weights before exporting a dataset tree for SimpleTuner / AI Toolkit / sd-scripts. Source images and sidecars remain unchanged; a fingerprint and decision manifest are saved. Vision tagging and trainer-specific weight adapters are injectable; training with an installed trainer has not been validated. See [LoRA Dataset Curator](doc/lora_dataset_curator.en.md).

### Composition Template Extractor

Launch `python -m comfyui_support_tools.applications.composition_template` to extract normalized composition regions, negative space, a saliency proxy, and an optional horizon from an image. The GUI supports manual traces, role edits, wireframe review, aspect-ratio adaptation, JSON/library storage, and generic generation-guidance export. The built-in extraction is a low-confidence heuristic that excludes color, identity, and style. Pose, semantic segmentation, depth, and vanishing-point adapters can be injected but are not bundled, and live integration with #348/#56/#82/#84/#354 is not implemented. See the [Japanese guide](doc/composition_template.md) / [English guide](doc/composition_template.en.md).

### Manga Creator / Storyboard

Launch `python -m comfyui_support_tools.applications.manga_creator` to edit a resumable MangaProject with Character/Location/Prop bibles, story-to-page/panel storyboard planning, four-koma/manga/webtoon/splash layouts, separate dialogue/balloon overlays, continuity events, best-of-N candidate storage, local panel regeneration, page composition, and JSON save/resume. The default backend draws rough storyboard sketches. Set `COMFYUI_MANGA_WORKFLOW` to an API-format workflow JSON to connect ComfyUI. Generic workflows receive text grounding but no automatic reference-image conditioning. MangaFlow/DiffSensei integrations, #348/#350/#353 routing, Job Queue, bundled vertical Japanese CJK fonts, story/identity/OCR evaluation, local inpaint repair, and PDF/CBZ export are not connected. See the [Japanese guide](doc/manga_creator.md) / [English guide](doc/manga_creator.en.md) for the implemented scope and validation.

### Expression Retouch

Launch `python -m comfyui_support_tools.applications.expression_retouch` for face selection, expression presets, local mask painting/erasing, a ComfyUI inpaint workflow, candidate comparison, and source/mask/history storage. OpenCV Haar face-part regions and identity signals are proxies; a semantic expression evaluator is injectable. Set the workflow and image/mask node IDs using `EXPRESSION_RETOUCH_*` environment variables. See the [Japanese guide](doc/expression_retouch.md) / [English guide](doc/expression_retouch.en.md).

### LoRA Composition Lab

`comfyui_support_tools.shared.lora_composition` provides compatibility preflight; LoRA update norm, cosine, subspace, and sign-conflict analysis; weighted, top-K, and Zip-style training-free merging; rank compression; global/per-layer scale-grid search; a fixed-seed evaluator bridge; user scale-preference priors; and safetensors plus runtime-recipe export with provenance. Install optional dependencies with `pip install -r requirements-lora-composition.txt`. Dense analysis is limited to 8,388,608 elements per layer. The Zip-style and top-K methods are comparable training-free baselines, not reproductions of the research papers. GUI and image-generation/evaluator adapter integration remain unimplemented. See [LoRA Composition Lab](doc/lora_composition.en.md).

### Image Dataset Classifier / Sorter

`comfyui_support_tools.shared.dataset_classifier.DatasetClassifierApplication` provides recursive inventory, an axis-classifier registry, weighted multi-evidence fusion, metadata precedence, alternate-label/disagreement/uncertainty reporting, persisted manual review, AND/OR/NOT queries, a style-embedding clustering adapter, dry-run/copy/move/manifest-only actions, collision avoidance, and verified caption/metadata sidecar transfer. JSON sidecar labels take priority over model evidence by default, and queries can classify only the axes they need. Export manifests record sources/destinations, labels, confidence, evidence provenance, and manual overrides; a #356 handoff payload is available.

Pretrained character/situation/background/style classifiers and embedding models are not bundled. Axes without registered adapters remain `uncertain`. This is a shared service using local JSON metadata or user-provided models; the complete review GUI and production semantic-model integrations from issue #369 remain unfinished.

### Generation parameters

Random Image CFG, steps, resolution, and sampler resolve through the shared `ParameterSpecRegistry`. Seed, scheduler, custom parameters, and backend-namespaced values can be added through spec registration. Resolved values preserve the existing four-field representation and store extensions under `parameters` / `backend_parameters`. UI and presets can share the registry schema descriptors.

### Output artifacts

The shared `output_artifact` helper provides fail, skip, overwrite, rename, and versioned conflict policies, source-path collision protection, fsynced temporary writes, validation before commit, and atomic publication. Inspector sidecar export uses it to validate JSON before publishing.

### MMD Model Doctor foundation

`comfyui_support_tools.shared.mmd_doctor` safely reads PMX 2.0/2.1 structures and reports bone hierarchy, weight, morph-reference, rigid-body, joint, and soft-body findings with localized repair candidates. Repairs never overwrite the source. When a motion evaluator is injected, the service compares candidates with Best-of-N and writes the selected PMX plus before/after findings and byte-level rollback data to separate files. External MMD physics engines and weight estimators can be connected through adapters.

This stage does not bundle PMX 2.1 soft-body support, a GUI, an MMD Bullet motion evaluator, or weight-estimation models such as SkinTokens/UniRig. Files containing soft bodies are rejected to avoid partial audits. Without an evaluator, automatic selection and export are disabled.

### MMD Camera Director基盤

`comfyui_support_tools.shared.camera_director` はdance VMDを読み、style preset・stage bounds・任意のPCM WAV energy sectionsからcamera VMD、JSON plan、animated GIF preview、SVG storyboardを生成します。heuristic backendは固定seedで再現でき、指定frame区間だけ再生成できます。DanceStyleCam用adapterとmodel-aware collision checkerは注入可能で、成果物は既存ファイルを上書きせず一式として保存します。

既定解析はroot bone名または最初のbone trackをsubject proxyに使い、WAVは一定長windowのRMS energyに分けます。DanceStyleCam本体、PMX/stage形状に基づく可視性・衝突検査、beat/section推定、3D scene renderer、timeline GUIは含まれていません。GIFとSVGはcamera planを可視化し、3D scene自体はrenderしません。

### MMD Camera Director foundation

`comfyui_support_tools.shared.camera_director` reads dance VMD and generates a camera VMD, JSON plan, animated GIF preview, and SVG storyboard from a style preset, optional stage bounds, and optional PCM WAV energy sections. Its heuristic backend is reproducible with a fixed seed and can regenerate only a selected frame interval. DanceStyleCam and model-aware collision checking can be injected as adapters; outputs are written as a non-overwriting artifact set.

By default, subject tracking uses a root-bone name or the first bone track, and WAV audio is divided into fixed-size RMS energy windows. DanceStyleCam itself, PMX/stage-geometry visibility and collision checks, beat/section inference, a 3D scene renderer, and a timeline GUI are not included. GIF and SVG visualize the camera plan; they do not render the 3D scene.

### Audio-to-MMD Face基盤

`comfyui_support_tools.shared.audio_to_face` はPCM WAVとtranscript、または注入したspeech analyzerからtimed phonemeを受け取り、日本語vowel morph・emotion morph・seeded blink curveを作成します。PMX固有morph名/rangeは `MorphCalibration` で指定でき、facial-only VMDとbody VMDへの非破壊morph merge、timing report、morph curve GIFを保存します。モデル名や既存成果物を壊さないため出力は上書きせず作成します。

既定のtranscript経路はmoraを音声全体へ均等配分する概算で、実際のspeech timingやlip-sync品質を保証しません。音声認識、phoneme alignment、歌唱/音素解析には外部 `SpeechAnalyzer` adapterが必要です。AnyTalk本体、PMX自動morph検出・calibration、gaze/head motion、preview videoは同梱していません。評価値は生成timelineの整合性指標であり、正解ラベルとの音声/映像比較ではありません。

### Audio-to-MMD Face foundation

`comfyui_support_tools.shared.audio_to_face` accepts timed phonemes from PCM WAV plus a transcript, or from an injected speech analyzer, then generates Japanese vowel morphs, emotion morphs, and seeded blink curves. `MorphCalibration` supplies model-specific morph names and ranges. The service writes a facial-only VMD, a non-destructive morph merge into a body VMD, a timing report, and a GIF of the morph curves without overwriting existing outputs.

The built-in transcript path distributes mora uniformly across the audio as an estimate; it does not provide real speech timing or guarantee lip-sync quality. Speech recognition, phoneme alignment, and singing analysis require an external `SpeechAnalyzer` adapter. AnyTalk itself, automatic PMX morph discovery/calibration, gaze/head motion, and preview video are not bundled. Evaluation values measure generated-timeline consistency, not comparison against labeled audio/video ground truth.

### Video-to-MMD Motion基盤

`comfyui_support_tools.shared.video_to_mmd` は外部pose recovery backendのtracked 3D skeletonをperson idで選択し、camera translation補正、confidenceベースの欠損補間、temporal smoothing、foot-contact補正、retarget、速度制限、keyframe reductionを行いVMD・confidence report・GIF previewを作成します。source bone/target PMX boneの対応と座標系は `RetargetProfile` で指定します。出力3ファイルは既存成果物を上書きせず作成します。

GVHMR/WHAM/DWPoseなどのvideo inference、本物のcamera estimation、person tracking、PMXのIK/geometryを使った適用previewは含みません。foot-contact補正はbackendが示すfoot contactとretarget bone名に依存する保守的なtranslation補正です。GIFはmapped boneの2D軌跡表示で、MMD scene renderingではありません。#376へのreference motion登録も自動では行いません。

### Video-to-MMD Motion foundation

`comfyui_support_tools.shared.video_to_mmd` selects a tracked 3D skeleton by person ID from an injected pose-recovery backend, then applies camera-translation compensation, confidence-based interpolation, temporal smoothing, foot-contact correction, retargeting, speed limiting, and keyframe reduction. It writes a VMD, confidence report, and GIF preview. `RetargetProfile` defines source-to-target bone mappings and coordinate conversion. The three outputs are created without overwriting existing files.

Video inference such as GVHMR/WHAM/DWPose, actual camera estimation, person tracking, and a PMX IK/geometry preview are not included. Foot-contact correction is a conservative translation adjustment that depends on backend contact labels and retarget bone names. The GIF shows mapped bones in 2D; it does not render an MMD scene. Registering the result as a #376 reference motion is also not automatic.

### Pixel Art Creator共通基盤

`comfyui_support_tools.shared.pixel_art` はText/Image/Retouchの共通grid、palette、size presets（8〜256）、transparent RGBA export、nearest-neighbor preview、deterministic metric/evaluator、sprite sheet cell utilities、undo/redo project historyを提供します。`PixelArtWindow` は3入口を一つのUIで選び、Image変換とRetouchは共通pipelineを使います。Text生成では `Text backend…` からローカルComfyUI API-format workflowを設定できます。対応workflowとComfyUI環境は利用者が用意し、model/LoRAは同梱しません。native readabilityやoutline指標はheuristic proxyで、semantic qualityは人の確認が必要です。

Retouch UIはpixel-level pencil/eraser/line/rectangle/fill、mirror、exact-color replacement、palette reduction、binary-alpha cleanup、isolated-pixel/outline cleanup候補を提供します。automatic cleanupはcandidate選択後にだけapplyでき、変更pixelをmagenta overlayとpixel count/region boundsでレビューできます。

standalone `python -m comfyui_support_tools.applications.pixel_art` の既定起動ではText backendを設定しないためText生成には対応backendの注入が必要です。#372/#373/#374の独立した生成器を自動で呼び出すadapterはまだ接続していません。palette-aware diffusion、生成AIのsemantic judge、tile/sprite編集UIも同梱していません。

### Shared Pixel Art Creator foundation

`comfyui_support_tools.shared.pixel_art` provides common Text/Image/Retouch grids, palettes, 8–256 size presets, transparent RGBA export, nearest-neighbor previews, deterministic metrics/evaluation, sprite-sheet cell utilities, and undo/redo project history. `PixelArtWindow` exposes all three entries in one UI; Image conversion and Retouch share the same pipeline. Text generation can be configured with a local ComfyUI API-format workflow through `Text backend…`; users provide the compatible workflow and ComfyUI installation, and no model or LoRA is bundled. Native readability and outline measures are heuristic proxies; semantic quality still needs human review.

The Retouch UI provides pixel-level pencil/eraser/line/rectangle/fill, mirror, exact-color replacement, palette reduction, binary-alpha cleanup, and isolated-pixel/outline cleanup candidates. Automatic cleanup only applies after candidate selection; changed pixels are reviewable with a magenta overlay, changed-pixel count, and region bounds.

The standalone `python -m comfyui_support_tools.applications.pixel_art` launch does not configure a Text backend by default, so text generation requires an injected compatible backend. Adapters that call the independent #372/#373/#374 generators are not wired automatically. Palette-aware diffusion, an AI semantic judge, and tile/sprite editing UI are not bundled.

### Music-to-MMD Dance基盤

`comfyui_support_tools.shared.music_to_mmd` はWAVと任意FFmpeg decoderによる音声読込、RMS/onset/BPM推定、energy基準の粗い楽曲section、beat-aligned choreography plan、差し替え可能なsection-generation backend、MMD標準bone profileへのretarget、floor/contact補正、VMD export、section単位rerollと評価レポートを提供します。既定の `procedural_baseline` はofflineで再現できるbeat/style連動のprocedural motionを作ります。

既定backendは学習済みfull-body dance modelではなく、作品としての振付品質・実歌詞/chorus意味理解を保証しません。sectionラベルはenergy heuristicです。PMX geometry、IK、skirt/hair physics previewは含まず、floor/contact指標もbone名とcontact labelに基づくproxyです。AtomicDance/ChoreDiffusion等はbackend adapterとして追加できますが、同梱・接続されていません。

### Music-to-MMD Dance foundation

`comfyui_support_tools.shared.music_to_mmd` provides audio loading through WAV and an optional FFmpeg decoder, RMS/onset/BPM estimates, coarse energy-based song sections, a beat-aligned choreography plan, replaceable section-generation backends, retargeting through an MMD bone profile, floor/contact correction, VMD export, per-section reroll, and evaluation reports. The default `procedural_baseline` creates deterministic offline motion modulated by beat and style.

The default backend is not a trained full-body dance model and does not guarantee choreography quality or understand lyrics/chorus semantics. Section labels are energy heuristics. PMX geometry, IK, and skirt/hair physics previews are not included; floor/contact metrics are proxies based on bone names and contact labels. AtomicDance/ChoreDiffusion and similar systems can be added through backend adapters but are not bundled or connected.

### MMD Character Creatorの検証基盤

`comfyui_support_tools.shared.mmd_character` はstable humanoid/free-3D routeのadapter contract、mesh/標準bone/skin weights/morph/physics検証、最大3回の局所repair loop、provenance/license確認、PMX exportとpreview adapter境界を提供します。Validation errorが残る候補はexportしません。

このrepositoryにはCharacterGen/Hunyuan3D/VRM/SkinTokens等の生成・autorig adapter、既定PMX binary writer、PMX renderer/physics previewがありません。`MmdCharacterCreator` でPMXを作るには外部backendを登録する必要があり、standalone end-to-end character generationはまだ構成されていません。髪/服のphysicsやあいうえおmorphもadapter生成結果が必要です。

### MMD Character Creator validation foundation

`comfyui_support_tools.shared.mmd_character` provides stable-humanoid/free-3D adapter contracts, mesh/standard-bone/skin-weight/morph/physics validation, up to three local repair rounds, provenance/license checks, and PMX export/preview adapter boundaries. Candidates with remaining validation errors are not exported.

This repository does not include CharacterGen/Hunyuan3D/VRM/SkinTokens generation or auto-rigging adapters, a default PMX binary writer, or a PMX renderer/physics preview. `MmdCharacterCreator` requires an external backend to create a PMX; standalone end-to-end character generation is not configured yet. Hair/clothing physics and Japanese vowel morphs also depend on adapter-generated data.

### Image-to-Pixel structure-aware workflow

The shared image workflow now offers `faithful`, `simplified`, `sprite`, `icon`, and `palette_constrained` conversions, four human-reviewable candidates, crop and dither controls, and recursive batch conversion with a JSON manifest that preserves relative paths. `sprite` uses transparent-alpha bounds to crop margins; it does not run an object detector. Candidate metrics and readability remain deterministic proxies, not semantic-quality judgments.

共通Image workflowは `faithful` / `simplified` / `sprite` / `icon` / `palette_constrained`、レビュー可能な4候補、crop/dither選択、relative pathとJSON manifestを保持するrecursive batch変換を提供します。`sprite` modeは透明alpha boundsを使って余白をcropします。object detectorは実行しません。候補metric/readabilityはsemantic品質の判定ではなくdeterministic proxyです。
