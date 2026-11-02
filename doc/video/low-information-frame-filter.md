# 動画フレームの低情報フィルター

[English](low-information-frame-filter.en.md)

`comfyui_support_tools.shared.video_frame_filter` は正規化済みフレームを安価なCPU特徴量で評価し、frameごとの `FrameFilterReport` と `FrameFilterBatchManifest` を返します。初期状態は無効です。黒/白比率、輝度entropy、edge density、sharpness、任意OCR text box、任意のsubject/saliency score、前後フレームの情報を融合し、`keep` / `drop` / `review` / `error` と理由・confidenceを記録します。decode failureは品質判定から分離されます。

`filter_existing_frame_folder` は既存画像フォルダーを再帰的・決定的順序で分析します。dry-runはレポートのみ返し、書き込みません。applyは入力を変更せず、出力全体を一時フォルダーへ作成・検証後、`kept/`・`rejected/`・`review/`・`errors/`とJSON manifestをまとめて公開します。途中で失敗した場合は一時出力を破棄します。`mark_only`では画像をコピーせずmanifestだけを作ります。出力先が入力と重なる場合、symlinkがある場合、既存出力を上書きする場合は拒否します。

Movie Frames UIにはfilter enable（既定OFF）、conservative/balanced/aggressive/custom preset、各ruleのtoggle、action、title/credits policy、custom presetの主要thresholdがあります。設定はpresetへ保存できます。`preview only`が既定で有効なため、最初はcountだけを確認し、applyを選んだ後に現在のMovie Frames出力を保ったまま`<video>_filtered`へ結果をコピーします。既存フレームfolder用の独立ボタンもあります。applyは非破壊で既存ファイルを上書きしません。

テキスト検出は `FrameTextBox` を返すlocal Tesseract adapterを使います。filterを有効にしてtext-onlyまたはtitle/credits ruleを使う場合、Tesseract executableと言語データが必要です。`auto`は`jpn`と言語データが両方あれば`jpn+eng`、それ以外は`eng`を使います。Tesseractがない場合はOCR rulesを無効にするか、Tesseractを導入します。OCRの生テキストはmanifestへ保存せず、engine versionだけをprovenanceへ記録します。subject/saliency scoreは任意入力です。高コストVLMは自動実行しません。現行UIのfilterはFFmpegが出力した画像を読み込んで評価します。事前にfinal imageへencodeせずdecodeから評価する手順は、共通解析APIへ正規化済みフレームを渡す将来のdecoder adapter接続が必要です。

## 使用例

```python
from pathlib import Path

from comfyui_support_tools.shared.contracts.frame_filter import FrameFilterOptions
from comfyui_support_tools.shared.frame_filter_application import filter_existing_frame_folder
from comfyui_support_tools.shared.tesseract_text_detector import TesseractTextDetector

options = FrameFilterOptions(enabled=True)
preview = filter_existing_frame_folder(
    Path("frames"), Path("filtered"), options, text_detector=TesseractTextDetector()
)
print(preview.kept_count, preview.dropped_count, preview.review_count)
```

`FrameFilterOptions` はfilter全体のOFF/ONと、個別black/white/transition/text-only/title-credits/low-detail/blur/neighbor togglesを持ちます。threshold presetsは誤削除を避けるため低confidenceの候補をreviewへ残します。`custom`ではextreme ratio、candidate score、title score、structure protection thresholdを指定できます。title/credits policyは `keep` / `drop` / `separate` から選びます。`separate`は別bucketへcopyし、元画像は残します。

## 検証と制約

synthetic fixtureでpure black/white、暗いtexture、白背景のsubject、通常字幕付きscene、OCR text-only、title policy、隣接sceneとの暗転、decode error、dry-run、別folder copy、apply失敗時のcleanup、mark-only、source保持を検証します。これらのfixtureは実動画のfalse-drop率を示すbenchmarkではありません。fade/blurは限定的なneighbor heuristicであり、near-duplicateはfeatureとして報告するだけで自動削除しません。永続subtitle overlayへの専用判定、adaptive per-video calibration、interactive review GUI、実データbenchmark、digest application連携は未実装です。filter前のdry-runと対象画像を確認し、aggressive presetはdatasetで評価してから使ってください。
