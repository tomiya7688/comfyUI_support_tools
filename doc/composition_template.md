# Composition Template Extractor

[English](composition_template.en.md)

`python -m comfyui_support_tools.applications.composition_template`で起動します。画像を開いてAuto extractを実行すると、画像サイズに依存しない0〜1座標で主領域候補、余白、注目度グリッド、reading flow、簡易horizon候補を作成します。Canvas上をドラッグしてregionを追加し、roleを編集できます。テンプレートはJSONへexport/importでき、ユーザーライブラリは`~/.comfyui_support_tools/composition_templates`に保存します。

## 設計と制約

- `CompositionTemplate`は配置、領域role、視線/深度/perspectiveの幾何情報だけを保存します。source pixel、色、衣服、identity、artist/styleの属性は含みません。provenanceにはsource SHA-256、元画像寸法、利用した手法、警告が含まれます。
- 標準抽出はPillowとNumPyによるcontrast/edgeベースのsaliency proxyです。人物や物体の意味を認識せず、subject boxは低信頼度の近似です。誤検出を手動修正してください。source pathや画像本体は保存されません。
- Pose、semantic subject detection、relative depth、vanishing pointの処理境界はProtocol adapterとして定義しました。特定modelやweightsは同梱せず、model-backed測定を行うには利用者がadapterを注入します。horizonも標準では粗いheuristic推定です。
- FITは幾何を保って余白を追加し、CROPは画面外の部分を切り取ります。SMART REFLOWは主領域を検出されたnegative space方向へ少し移動する単純な配置補助で、意味理解や複雑なpolygon reflowは行いません。いずれもstretchしません。
- JSONはschema version付きで2 MiBに制限し、未知field、座標範囲外、重複region IDを拒否します。library保存は既存名を上書きしません。
- Guidance exportは下流consumer向けの汎用JSON payloadです。#348/#56/#82/#84/#354への実接続やComfyUI workflow自動生成はこの変更に含まれません。

必要な画像依存は既存環境のPillowとNumPyです。GUI起動にはTkが必要です。
