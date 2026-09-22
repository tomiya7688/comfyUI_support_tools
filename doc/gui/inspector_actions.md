# Inspector / Media Action — #220 Phase 1

`KadokaTools.exe --new-ui`（開発: `python tabbed_tools_gui.py --new-ui`）。
旧GUIの通常起動は変更しない。#219 Browserから選択中のメディアをInspectorへ渡す。

## 操作

1. Browserで画像を1〜60件選択。Inspectorで画像/動画/複数選択を区別する。
2. `Tagger API設定・接続確認`でHTTP(S)のinterrogate URLを入力する。
   対応: `/pixai/v1/interrogate`、`/tagger/v1/interrogate`（reverse proxyのprefix可）。
   モデル、Tag閾値、Character閾値、timeoutを指定する。
3. 「接続確認・モデル一覧」は同じprefixの `/interrogators` へGETする。
   接続確認後、一覧にあるモデルを設定する。URL変更時は確認結果を破棄する。
4. Inspectorの実行ボタン、上部Actions、Browserの右クリックまたはShift+F10から
   `Tag / 内容タグ付け`を実行。**宛先URL・モデル・画像数・元画像データの送信**を確認する。
   右クリック対象が既存の複数選択内なら選択を保持し、空白なら解除する。
5. 結果は各MediaItemの内容Tagsへ反映。Style、Prompt、Negative Prompt、Character、
   Dataset/LoRAメモは別fieldのまま保持する。画像単一選択で手動メモも編集できる。
6. 手動編集は「メモをセッションに反映」で確定する。未反映の編集は選択切替時に破棄し
   ログへ通知する。未反映メモがある間は画像送信を行わない。
7. 停止要求は現在のHTTP通信/timeoutの完了後に次の画像を止める。

## 実装範囲と制限

- 実動作ActionはTagのみ。既存 `scripts/tabs/folder_tagger.py` の
  `_interrogate_bytes` と同じHTTP契約を使い、Tabやserver内部をimportしない。
- 接続確認はモデル一覧の疎通確認で、推論の正常性を保証するものではない。
  未接続・モデル不一致はdisabled、処理時のHTTP/JSON/ファイルエラーは項目別に表示。
- Style Analyzer、Img2img、Dataset登録、Character Replace、Variations、Video Actionsは
  **adapter未実装の理由を表示してdisabled**。メモの入力はこれらの処理実行を意味しない。
  生成設定・学習設定、永続保存、共通Job Queueは今回実装していない（#5/#221/#222/#223）。
- 画像のみ。動画/混在選択を黙って部分実行しない。画像は20MiB/40MP以下、
  animated GIF/WebP等の複数フレーム画像はエラー（旧Folder Taggerの全機能移植ではない）。
- タグ結果は既存の内容Tagsを置き換える。他fieldは保持。閾値未満を除外する。
  StyleをTagレスポンスの別fieldから勝手に混入しない。
- 全てWorkspaceセッション内。元画像・隣接TXT/metadataを書き換えず、ファイルを追加しない。
  旧GUIへの切替/ウィンドウ終了でメモとAPI設定を破棄。書き戻し/移行は今後の作業。
- metadataはBrowserのpath/type/size、プレビューの画像寸法/動画秒数。
  EXIF全文・PNG生成情報の自動解析は含まない。
- 実行開始時のimmutable選択snapshotへ結果を返す。途中の選択変更で別画像へ結果を
  誤反映しない。再選択時にsize/mtimeが変わったメディアの古いメモは破棄する。
- 1操作のみ実行し、裏に無制限のjob queueを作らない。結果queue64件、batch最大60。
  notes最大4096項目、手動メモfield最大8192文字/合計32768文字、Tag結果最大16384文字。
- API応答上限1MiB、モデル数256、タグ数2000。未知の形式・nonfinite confidence等はエラー。
- HTTP proxyの環境自動探索なし、redirectを追跡せず、URL内credentials/queryを拒否。
  HTTPSは同梱certifi CAで検証する。サーバー本文や画像base64はログへ出さない。
- GUIは通信を待たない。タイムアウトはブロッキングIO単位であり操作全体の厳密deadlineではない。
  終了時は協調停止する。すでに送信したHTTP要求をサーバー側で取り消す契約はない。

## 構造 / 拡張

`entrypoints/inspector.py` がこのMain GUI内のUI/Process/Dataを配線する。
UI Commander -> UI Messenger -> Process Messenger -> Process Commander。
Process ProcessingがAction availability、選択snapshot、session notes、Tag意味解析を担当。
IOはProcess Messenger -> Data Messenger -> Data Commander -> Data Processing。
別ApplicationとはHTTPだけで通信する。モデル本体・venv・site-packages・server scriptは不要。

新Actionは `process/processing/media_actions.py` の定義とGUI非依存handlerを同時に追加する。
利用可能と表示するだけのplaceholderは禁止。UIの3導線は同じ定義/dispatcherを使う。
#5のシーケンス基盤は未完成のため、このtyped command facadeを将来接続する。
#220は全adapter完成として閉じず、このPhase 1の根拠を記録する。

## 検証

`python -m unittest tests.test_inspector_actions tests.test_inspector_actions_ui`

Linux Tkにはdisplayが必要（例: Xvfb）。Windows CIはGUIを含む全testを実行する。
localhostのfake HTTPサーバーでprotocol/実payload、複数画像、壊れた画像、モデル不在、
redirect拒否、停止、選択切替、Notes/Style分離、同じmenu/button dispatchを検証する。
`--shell-smoke-test` は凍結exe内から合成画像とloopback fake Taggerで同じ経路を通す。
**fakeによる契約試験であって実AIモデルの精度/実サービス互換性検証ではない**。
Python完全未導入のWindows VM試験とも区別する。

API参照:
- Python urllib.request（ProxyHandler、HTTPRedirectHandler、timeout）
  https://docs.python.org/3/library/urllib.request.html
- 既存Tagger契約: `scripts/tabs/folder_tagger.py` `_refresh_models` / `_interrogate_bytes`
