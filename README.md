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

`comfyui_support_tools.shared.pixel_art` はText/Image/Retouchの共通grid、palette、size presets（8〜256）、transparent RGBA export、nearest-neighbor preview、deterministic metric/evaluator、sprite sheet cell utilities、undo/redo project historyを提供します。`PixelArtWindow` は3入口を一つのUIで選び、Image変換とRetouchは共通pipelineを使います。Text生成は差し替え可能な `PixelTextBackend` を注入します。native readabilityやoutline指標はheuristic proxyで、semantic qualityは人の確認が必要です。

standalone `python -m comfyui_support_tools.applications.pixel_art` の既定起動ではText backendを設定しないためText生成には対応backendの注入が必要です。#372/#373/#374の独立した生成器を自動で呼び出すadapterはまだ接続していません。palette-aware diffusion、生成AIのsemantic judge、tile/sprite編集UIも同梱していません。

### Shared Pixel Art Creator foundation

`comfyui_support_tools.shared.pixel_art` provides common Text/Image/Retouch grids, palettes, 8–256 size presets, transparent RGBA export, nearest-neighbor previews, deterministic metrics/evaluation, sprite-sheet cell utilities, and undo/redo project history. `PixelArtWindow` exposes all three entries in one UI; Image conversion and Retouch share the same pipeline. Text generation uses an injected replaceable `PixelTextBackend`. Native readability and outline measures are heuristic proxies; semantic quality still needs human review.

The standalone `python -m comfyui_support_tools.applications.pixel_art` launch does not configure a Text backend by default, so text generation requires an injected compatible backend. Adapters that call the independent #372/#373/#374 generators are not wired automatically. Palette-aware diffusion, an AI semantic judge, and tile/sprite editing UI are not bundled.
