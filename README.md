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

### Video to MMD Motion

`comfyui_support_tools.shared.video_to_mmd` は、GVHMR/WHAM等を差し替える姿勢推定backend contract、confidence付き3D pose retarget、カメラ平行移動の除去、足接地・速度制限・key reduction、VMD 0002出力を提供します。実際の姿勢推定model、動画decoder、PMX geometry/IK previewは同梱していません。

### Music to MMD Dance

`python -m comfyui_support_tools.applications.music_to_mmd` でstandalone editorを起動できます。`comfyui_support_tools.shared.music_to_mmd.MusicToMmdApplication` は、音源解析・編集可能なsection plan・dance backend registry・sectionごとの生成/再生成・Video-to-MMDのretarget/foot contact cleanup・VMD出力をつなぎます。既定decoderは10分以下の非圧縮PCM WAVで、PATHにFFmpegがあればMP3/FLAC等も読み込めます。style/energy/section/beatから関節列を作るoffline procedural baselineを含みます。より高品質な生成にはAtomicDance/DanceLDM等の3D dance model adapterを追加します。RMS onset/BPMと8秒単位のenergy sectioningは軽量heuristicで、chorus等の意味解釈はレビュー対象です。

このcoreはoffline procedural baselineを提供しますが、学習済み外部dance model、PMX geometry/physics preview、IK solver、collision evaluatorを同梱しません。procedural motionは編集とpipeline検証用で、trained dance backend相当の振付品質を保証しません。評価レポートはbeat activity、smoothness、foot contact drift、floor clearance、section diversityのproxyと各制約を分けて記録します。

### MMD Character Creator

`comfyui_support_tools.shared.mmd_character` はStable humanoid/Free 3D route、CharacterSpec、geometry/rig/morph/physics/preview/export adapter contracts、標準bone・mesh topology・weights・morph・material・physics validator、provenance/license gate、最大3回の局所repair loopを提供します。invalid rig/geometryとunknown model licenseはPMX exporterへ渡しません。

CharacterGen/Hunyuan3D/VRM/SkinTokens/UniRig generatorとBlender `mmd_tools` PMX exporter/preview adapterはまだ接続されていません。従ってこの変更はproduction-ready model generationを提供せず、Character Creator acceptanceのうち実際のPMX生成、顔morph、cloth physics、motion previewは未完了です。外部adapterを登録して初めて出力できる構成で、対応実装がない場合は明確に失敗します。

### Image Dataset Classifier / Sorter

`comfyui_support_tools.shared.dataset_classifier.DatasetClassifierApplication` は再帰inventory、axis classifier registry、複数evidenceの重み付きfusion、metadata優先、alternate label/disagreement/uncertain分類、manual review保存、AND/OR/NOT query、style embedding clustering adapter、dry-run/copy/move/manifest-only、collision回避、caption/metadata sidecar検証付き転送を提供します。JSON sidecarのlabelは既定priorityで他model evidenceより優先し、queryは必要なaxisだけを分類できます。結果manifestにはsource/output、labels、confidence、evidence provenance、manual overrideを記録し、#356向けhandoff payloadも作れます。

character/situation/background/styleの学習済みclassifierやembedding modelは同梱せず、adapter未登録のaxisは`uncertain`になります。ローカルJSON metadataと利用者が登録するmodelsを使うshared serviceです。GitHub issue #369の完全なreview GUIと本番semantic model接続は未実装です。

### Pixiv Dataset Downloader

`comfyui_support_tools.shared.pixiv_dataset` はPixivPy3 source adapter、refresh-token auth/health、tag・creator・bookmark・ranking・ID query、filter、rate limit/retry、JobRuntime bridge、resume checkpoint、ページ順を維持したillustration/mangaとugoira archive収集、任意GIF/WebP preview、work/provenance JSON、exact/perceptual duplicate grouping、#356 handoffを提供します。`PixivRateLimitProfile`で毎分上限、API/download並列上限、interval、retry/backoff、429 cooldown、自動pauseをapp/query/job単位に設定でき、effective設定とbounded retry/429履歴をcheckpointへ記録します。custom設定が保守的な初期値を超える場合はwarning状態を返します。使う場合は別環境に `pip install -r requirements-pixiv.txt` でPixivPy3を導入し、呼び出し元のsecure secret storeからrefresh tokenを実行時に渡してください。tokenをpresetやdatasetへ保存しません。

このbackendはAPI接続型で、認証情報と実Pixiv応答がない環境では実アカウントへの通信を実行しません。GUIのquery builder/preview controls、CLI command、翻訳tag辞書、非original派生画像の取得、動画(MP4)変換は未実装です。権利許可は常に`unknown`として保存され、duplicateはgroup化のみで自動削除しません。詳細は[Pixiv Dataset Downloader](doc/dataset/pixiv_dataset.md)を参照してください。

### Modern Trainer Adapter Registry

`comfyui_support_tools.shared.trainer_registry` はSimpleTuner / AI Toolkit / sd-scriptsを共通`TrainingSpec`からtrainer別JSON/YAML/TOML/CLIへ変換し、SDXL/FLUX.1/FLUX.2/Qwen Image/SD3.5/Anima/Hunyuan/Krea2/HiDreamのarchitecture profile、LoRA/LyCORIS method status、version/capability cache、target module discovery、quantization/offload適合性、provenance、1–8 step smoke gateを提供します。Autoはruntimeでsupportedと確認されたmethodだけを選び、smokeでcheckpointとsampleが得られない場合はfull training callbackを実行しません。trainer実体とmodelを使ったlive validationは未実施です。詳細は[Modern Trainer Adapter Registry](doc/trainer_registry.md)を参照してください。

### LoRA Training Doctor

`comfyui_support_tools.shared.training_doctor` はcharacter/style/object/multi-concept向け固定validation matrix、同一seed/sampler/steps/resolutionのcheckpoint比較、trigger/strength sweep、task別weighted score、leakage/memorization/base-preservation/diversity signal、patience付きearly-stop callback、best checkpoint選択/rollback、training curveとsample preview付きreport保存を提供します。`ValidationEvaluator`は#20品質評価の実測値を受け取り、`publish_prompt_metadata`は#240互換sinkへtrigger/tags/strengthを渡します。trainer/ComfyUI実生成adapterはこの環境にないためlive integrationは未検証です。詳細は[LoRA Training Doctor](doc/training_doctor.md)を参照してください。

### LoRA Dataset Curator / Caption Planner

`python -m comfyui_support_tools.applications.lora_dataset_curator`でGUIを起動し、task-aware caption、Character Registryのtrait/outfit、quality proxy、duplicate group、coverage、validation split、sample weightを確認・手動修正してからSimpleTuner / AI Toolkit / sd-scripts向けdataset treeをexportできます。入力画像・sidecarは変更せず、fingerprintとdecision manifestを保存します。vision taggerとtrainer固有weight adapterは注入式で、実trainerによるtrainingは未検証です。詳細は[LoRA Dataset Curator](doc/lora_dataset_curator.md)を参照してください。

### LoRA Composition Lab

`comfyui_support_tools.shared.lora_composition` は互換性preflight、LoRA update norm/cosine/subspace/sign conflict分析、weighted/top-K/Zip-style training-free merge、rank圧縮、global/per-layer scale grid探索、seed固定の評価bridge、user scale preference prior、provenance付きsafetensorsとruntime recipe出力を提供します。任意依存は `pip install -r requirements-lora-composition.txt` で導入します。分析するdense updateは1 layerあたり8,388,608要素に制限します。Zip-style/top-Kは研究論文実装そのものではなく、比較可能なtraining-free baselineです。GUIと画像生成/evaluation adapterの統合は未実装です。詳細は[LoRA Composition Lab](doc/lora_composition.md)を参照してください。

### Pixel Art Creator

`python -m comfyui_support_tools.applications.pixel_art` で独立したPixel Art Creator画面を起動し、Text / Image / Retouchを選べます。`comfyui_support_tools.shared.pixel_art.PixelArtApplication` は3入口で共通設定と処理を使います。8/16/32/64/96/128/192/256 pxとcustom WxH、palette import/extract/export、透明RGBA、crop/pad、palette制限、dither、nearest-neighbor preview、native-sizeのpixel指標、PNG/JSON出力、undo/redo可能なproject履歴、sprite-sheet分割/結合を提供します。Text workflowでは `Text backend…` からローカルComfyUI API-format workflowを設定できます。アプリにはmodel/LoRAを同梱せず、適合するworkflowとローカルComfyUI環境は利用者が用意します。

Retouchでは1px pencil/eraser/fillに加えて、palette色の一括置換、減色、半透明edgeの二値化、isolated pixel・palette・輪郭の保守的なcleanup候補を選べます。候補を適用する前にnearest-neighbor preview、変更pixel数、変更領域、palette前後を確認でき、採用操作はundo/redo履歴に保存されます。semantic confidenceは未算出として報告し、cleanupは自動適用しません。

画像変換ではfaithful / simplified / sprite / icon / palette-constrained modeを選び、複数候補をnearest-neighbor previewとnative-size指標で比較できます。sprite modeはalpha boundsを使ったsubject crop、icon modeはsquare crop、batch modeは相対パスを保ったPNG/metadata出力とno-overwrite manifestを提供します。binary-alpha sourceの縮小では透明edgeを保持し、半透明sourceのalphaは維持します。semantic segmentation、pose/depth理解、生成モデルによる低解像度での意味再構成は接続されておらず、heuristic指標は主題保持の保証ではありません。

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
# Video-to-MMD motion recovery core

Issue #378 adds a backend-neutral video motion pipeline under
`comfyui_support_tools.shared.video_to_mmd`. Implementations of `PoseRecoveryBackend`
can wrap GVHMR, WHAM, or another pose model and return tracked 3D bone samples with
confidence, estimated camera translation, ground height, and foot-contact labels.
The shared core handles person selection, axis/scale retarget rules, camera translation
compensation, low-confidence interpolation, temporal smoothing, foot anchoring, speed
limiting, key reduction, and VMD 0002 bone-key serialization.

`convert_video_to_vmd(video_path, output_dir, backend, profile)` writes a VMD file,
JSON confidence/finding report, and a small animated 2D mapped-bone preview. It reserves
all three destination paths without overwriting existing files. Preview is a motion
debug aid and does not load PMX geometry, bone hierarchy/rest poses, IK, or a 3D renderer.
The repository does not bundle a video decoder, person detector/tracker, GVHMR model,
or trained pose weights. Those remain injectable backend responsibilities; detected
limitations are reported rather than implying geometric accuracy from the 2D preview.

## Music to MMD Dance

Launch the standalone editor with `python -m comfyui_support_tools.applications.music_to_mmd`. `comfyui_support_tools.shared.music_to_mmd.MusicToMmdApplication` connects audio analysis, editable section plans, a capability-routed dance backend registry, per-section generation/regeneration, the Video-to-MMD retarget/contact cleanup core, and VMD export. The default decoder accepts uncompressed PCM WAV files up to ten minutes and can read MP3/FLAC when FFmpeg is available on `PATH`. It includes an offline procedural baseline that builds joint motion from style, energy, sections, and beats. Add higher-quality 3D dance models such as AtomicDance/DanceLDM through adapters. RMS onset/BPM estimation and eight-second energy segmentation are lightweight heuristics; semantic labels such as chorus require review.

The core includes an offline procedural baseline but does not bundle a trained dance model, PMX geometry/physics preview, IK solver, or collision evaluator. Procedural motion supports editing and pipeline validation; it does not claim choreography quality equal to a trained dance backend. The report separates beat activity, smoothness, contact drift, floor-clearance, and section-diversity proxies from their stated limitations.

## MMD Character Creator

`comfyui_support_tools.shared.mmd_character` provides Stable Humanoid/Free 3D routes, CharacterSpec, geometry/rig/morph/physics/preview/export adapter contracts, standard-bone/topology/weight/morph/material/physics validation, provenance/license gating, and up to three local repair rounds. Invalid rigs/geometry and unknown model licenses never reach the PMX exporter.

CharacterGen/Hunyuan3D/VRM/SkinTokens/UniRig generation and a Blender `mmd_tools` PMX exporter/preview adapter are not connected yet. This change therefore does not provide production character generation; actual PMX generation, facial morph synthesis, cloth physics, and motion preview remain unimplemented acceptance items. Output requires registered external adapters and fails clearly when none are available.


### Image Dataset Classifier / Sorter

`comfyui_support_tools.shared.dataset_classifier.DatasetClassifierApplication` provides recursive inventory, an axis-classifier registry, weighted multi-evidence fusion, metadata precedence, alternate-label/disagreement/uncertainty reporting, persisted manual review, AND/OR/NOT queries, a style-embedding clustering adapter, dry-run/copy/move/manifest-only actions, collision avoidance, and verified caption/metadata sidecar transfer. JSON sidecar labels take priority over model evidence by default, and queries can classify only the axes they need. Export manifests record sources/destinations, labels, confidence, evidence provenance, and manual overrides; a #356 handoff payload is available.

Pretrained character/situation/background/style classifiers and embedding models are not bundled. Axes without registered adapters remain `uncertain`. This is a shared service using local JSON metadata or user-provided models; the complete review GUI and production semantic-model integrations from issue #369 remain unfinished.

### Pixiv Dataset Downloader

`comfyui_support_tools.shared.pixiv_dataset` provides a PixivPy3 adapter, refresh-token authentication and health checks, tag/creator/bookmark/ranking/ID queries, filtering, throttling and bounded retries, JobRuntime integration, resumable checkpoints, ordered illustration/manga pages and ugoira archives, optional GIF/WebP previews, work/provenance JSON, exact/perceptual duplicate grouping, and a #356 handoff. `PixivRateLimitProfile` configures requests/minute, API/download concurrency caps, interval, retries/backoff, 429 cooldown, and automatic pause at application/query/job scope; the effective policy is recorded in checkpoints and provenance, with bounded retry/429 history in job state. Aggressive custom profiles expose a warning state. Install PixivPy3 separately with `pip install -r requirements-pixiv.txt`; supply the refresh token at runtime through the caller's secure secret store. Presets and dataset files never store it.

This backend requires live Pixiv credentials and API responses for account-level validation, which are not available in the offline test suite. The query-builder GUI, CLI command, translated-tag dictionary, non-original rendition selection, and MP4 conversion are not implemented. Rights remain `unknown`; duplicate handling groups records and never deletes files. See [Pixiv Dataset Downloader](doc/dataset/pixiv_dataset.md).

### Modern Trainer Adapter Registry

`comfyui_support_tools.shared.trainer_registry` translates a shared `TrainingSpec` into trainer-specific SimpleTuner / AI Toolkit / sd-scripts JSON/YAML/TOML/CLI, and provides SDXL/FLUX.1/FLUX.2/Qwen Image/SD3.5/Anima/Hunyuan/Krea2/HiDream architecture profiles, LoRA/LyCORIS method states, versioned capability cache, target-module discovery, quantization/offload validation, provenance and a 1–8 step smoke gate. Auto selects only methods confirmed as supported at runtime; full-training callbacks do not run unless smoke produces both a checkpoint and sample. Live validation with installed trainers and model weights has not been performed. See [Modern Trainer Adapter Registry](doc/trainer_registry.en.md).

### LoRA Training Doctor

`comfyui_support_tools.shared.training_doctor` provides fixed character/style/object/multi-concept validation matrices, checkpoint comparisons under the same seed/sampler/steps/resolution, trigger and strength sweeps, task-weighted scores, leakage/memorization/base-preservation/diversity signals, patience-based early-stop callbacks, best-checkpoint selection/rollback, and report persistence with training curves and sample previews. `ValidationEvaluator` accepts measured #20 image-quality evidence, and `publish_prompt_metadata` sends trigger/tags/strength to a #240-compatible sink. No live trainer/ComfyUI generation adapter is configured in this environment, so live integration is unverified. See [LoRA Training Doctor](doc/training_doctor.en.md).

### LoRA Dataset Curator / Caption Planner

Launch the GUI with `python -m comfyui_support_tools.applications.lora_dataset_curator` to review and edit task-aware captions, Character Registry traits/outfits, quality proxies, duplicate groups, coverage, validation splits, and sample weights before exporting a dataset tree for SimpleTuner / AI Toolkit / sd-scripts. Source images and sidecars remain unchanged; a fingerprint and decision manifest are saved. Vision tagging and trainer-specific weight adapters are injectable; training with an installed trainer has not been validated. See [LoRA Dataset Curator](doc/lora_dataset_curator.en.md).

### LoRA Composition Lab

`comfyui_support_tools.shared.lora_composition` provides compatibility preflight; LoRA update norm, cosine, subspace, and sign-conflict analysis; weighted, top-K, and Zip-style training-free merging; rank compression; global/per-layer scale-grid search; a fixed-seed evaluator bridge; user scale-preference priors; and safetensors plus runtime-recipe export with provenance. Install optional dependencies with `pip install -r requirements-lora-composition.txt`. Dense analysis is limited to 8,388,608 elements per layer. The Zip-style and top-K methods are comparable training-free baselines, not reproductions of the research papers. GUI and image-generation/evaluator adapter integration remain unimplemented. See [LoRA Composition Lab](doc/lora_composition.en.md).

### Pixel Art Creator

Launch the standalone Pixel Art Creator window with `python -m comfyui_support_tools.applications.pixel_art` and select Text / Image / Retouch. `comfyui_support_tools.shared.pixel_art.PixelArtApplication` shares processing across these three entry workflows. It provides 8/16/32/64/96/128/192/256 px presets and custom WxH, palette import/extraction/export, transparent RGBA, crop/pad, palette limits, dithering, nearest-neighbor previews, deterministic native-size metrics, PNG/JSON export, undo/redo project history, and basic sprite-sheet split/pack. The Text workflow can use `Text backend…` to configure a local ComfyUI API-format workflow. The application does not bundle a model or LoRA; users provide a compatible workflow and local ComfyUI installation.

Retouch supports 1px pencil/eraser/fill, exact palette replacement, bounded palette reduction, partial-alpha edge cleanup, and reviewable conservative isolated-pixel/palette/outline cleanup candidates. Before applying a candidate, users can inspect its nearest-neighbor preview, changed-pixel count, changed regions, and before/after palette size. Accepted edits enter undo/redo history; semantic confidence is reported as unavailable and cleanup is never auto-applied.

Image conversion offers faithful / simplified / sprite / icon / palette-constrained modes and comparable candidates with nearest-neighbor previews and native-size metrics. Sprite mode uses alpha bounds for subject cropping, icon mode uses square cropping, and batch conversion preserves relative paths while writing PNG/metadata and a no-overwrite manifest. Downscaling binary-alpha sources preserves crisp transparency; existing partial alpha is retained. Semantic segmentation, pose/depth understanding, and model-based low-resolution semantic reconstruction are not connected, so deterministic metrics do not guarantee subject preservation. Pixel metrics remain heuristics for color count, isolated pixels, likely interpolated colors, and outline candidates; inspect native-size results, especially at small sizes.
