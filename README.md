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
