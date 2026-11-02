# 弱信号・レイヤー分離アプリケーション

## 目的

`shared.weak_signal` は、反射、グレア、紙の裏写り、ベール、弱い細部、照明むらを共通の観測・候補・証拠形式で扱います。手動モードと統計量に基づく仮モード選択を備え、OCRやInspectorへ渡せる候補画像とJSONマニフェストを書き出します。

```python
from comfyui_support_tools.shared.weak_signal import (
    ObservationInput, WeakSignalApplication, WeakSignalMode, WeakSignalRequest,
)

result = WeakSignalApplication().process(
    ObservationInput("scan-001", (encoded_png_bytes,)),
    WeakSignalRequest(mode=WeakSignalMode.PAPER_SHOWTHROUGH),
)
artifacts = WeakSignalApplication().export(result, output_dir)
```

`WeakSignalCandidate` は候補画像、名前付き測定値、信頼度、処理系、`OBSERVED` / `ENHANCED` / `INFERRED` / `COMPLETED` の来歴を保持します。exportされた `*.weak-signal.json` には候補、構成画像、来歴、OCR候補パスが含まれます。

## 実装済みバックエンド

標準のPillowバックエンドはローカル背景正規化、ハイライト抑制、コントラスト・細部強調の保守的な候補を生成します。弱細部では保守・自然・強調の比較候補を返します。出力には元の観測画像も `observed_input` として保持されます。

3枚以上の `burst` / `video` 反射入力は、呼び出し側がフレーム位置合わせ済みと宣言した場合に限り、3フレーム中央値と時間残差を計算します。時間残差はシーンの動きやノイズも含む推定成分であり、反射マスクではありません。単一画像の反射と透過の分離は観測だけでは一意に決まりません。

Toukaの透過面分離モードは、互換バックエンドが登録されていないため標準では選択できません。既存UIのTouka実行ファイルはCLIアプリとして動き、Pythonの共通候補契約には接続されていません。レジストリへ `WeakSignalBackend` 実装を注入すれば、ComfyUI連携やToukaアダプターをUI変更なしで追加できます。

## 入力上限と制約

入力はPNG/JPEG等のPillowが開ける画像バイト列で、最大16メガピクセル、最大512フレームです。`video` はデコード済みフレームを受け取る契約で、動画コンテナのデコード、フレーム位置合わせ、UIプレビューは担当しません。自動モードは明度・ヒストグラムの統計ヒューリスティックであり、意味理解ではありません。候補順位も構造保持率とコントラストの名前付き代理値で、実画質評価ではありません。

## 検証

`python -m unittest tests.test_weak_signal` で契約、候補生成、アラインメント前提、来歴マニフェストを検証できます。
