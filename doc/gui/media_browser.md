# Media Browser — #219

起動: `KadokaTools.exe --new-ui`（開発時: `python tabbed_tools_gui.py --new-ui`）。
引数なしの旧GUIは変更しない。#218 Shellの中央に実ファイルのBrowserを追加する。

## 操作

1. 中央の「分類」を Library / Dataset / Generated から選び、「フォルダを開く」。
   サブフォルダも読み込む。新しいフォルダを開くと現在の一覧を置き換える。
2. 左Libraryの Images / Videos / Dataset / Generated で絞り込み、中央の検索で
   ファイルパスを検索する（大文字小文字を区別しない、日本語対応）。
3. 名前 / 更新日時 / サイズ、昇順 / 降順を指定する。
4. サムネイルとリストを切り替える。1ページ60件、下部の前/次ボタンで移動する。
5. クリックで単一選択、Ctrl / Shiftで複数選択、Ctrl+Aで現在ページを全選択。
   右Inspectorへ選択件数・代表ファイル・画像または動画の静止フレームを表示する。
6. 動画のスライダーは指定位置の静止フレームを再取得する。連続再生・音声再生はしない。
7. 「★ 選択を切替」でお気に入りを切替。Favorites / Recentはセッション内のみ。
8. 「旧ツール一覧」で従来30ツールに到達できる。上部の機能検索は旧ツール用、
   中央の検索はメディア用。「メディア」でBrowserへ戻る。

小さいウィンドウではJobsを折り畳むか境界をドラッグしてBrowserを広げられる。
Inspectorは縦スクロール可能。未対応形式・破損ファイルはエラー表示だけで継続する。
再読込でファイルの追加/削除/更新を反映する。自動監視やファイル変更は行わない。

## メディアと状態の契約

- `shared/contracts/media_item.py`: frozen `MediaItem`。
  IDは正規化済み絶対パスのSHA-256。再走査で同じID、移動/改名時は別ID。
- collectionは選択したフォルダに対してユーザーが指定する分類。
  datasetの注釈形式・生成パラメータを自動解釈する機能ではない。
- `ShellWindow.media_selection` は不変のMediaItem tuple。
  `<<MediaSelectionChanged>>` をTk所有スレッドで発行し、#220のAction/Inspectorが購読できる。
- 絞り込みで隠れた項目・ページ外の選択は解除する。旧ツール表示中もAction対象は空。
- Favorites、Recent、読込フォルダはディスク保存しない。ウィンドウ終了や旧GUIへ移動すると
  Media Browserのセッションは終了する（旧ツールのRecentとは別）。

## IO / 負荷 / アプリ境界

UI Commander -> UI Messenger -> Process Messenger -> Process Commander。
検索・ソート・選択はProcess Processing、ローカルIOはProcess/Data Messenger経由で
Data Commander -> Data Processingへ委譲する。別Applicationの内部をimportしない。

- フォルダ走査用とデコード用のworkerは各1本、Tk呼び出しは所有スレッドだけ。
- 走査128件/batch、結果queueは8batch。旧フォルダのtokenを破棄し、切替時に走査を中断。
- 表示は60件/page。デコード待ちも最大60件、プレビュー結果queueは72件。
- デコーダ内のメモリLRUは最大128entryかつPNG payload合計16 MiB。
  キーはmedia ID / 実ファイルのsize・mtime_ns / preview size / video position。
- 画像プレビュー480px、サムネイル128px。EXIF回転を反映。40MP超は省略。
- 走査上限100,000件に到達した場合は明示表示。巨大なフォルダは小さく分けて開く。
  全件の無制限ロード・メモリ使用を許容する設計にはしない。
- 通常の対応拡張子: PNG/JPEG/WebP/BMP/TIFF/GIF、MP4/MKV/MOV/AVI/WebM/M4V。
  GIFは静止画、動画のデコード可否とseek精度は同梱OpenCVの対応コーデックによる。
- symlinkは追跡しない。ファイルは読み取りのみ。外部Python、CLI、プレイヤー、
  バックエンドAPI、別アプリ内部ディレクトリの自動探索を一切利用しない。
  Pillow/OpenCVは既存の同梱依存を使い、追加インストールを要求しない。
- 終了はworkerへ協調停止を通知する。実行中のOS/ネイティブデコーダ呼び出しを
  強制中断する保証はないが、GUI終了をその完了待ちで止めない。

## 検証

`python -m unittest discover -s tests -t . -p "test_media_browser_*.py"`

LinuxのGUIテストにはdisplayが必要（`xvfb-run -a`等）。Windows CIはGUIを含め実行する。
実際のPNG/JPEG/MJPG AVI、日本語/空白パス、破損画像、キャッシュ無効化、EXIF、
複数選択、切替、selection通知、表示/queue上限、停止を検証する。
10,000 MediaItemのページング検証と129実ファイルのGUI検証を含む。

既存 `--shell-smoke-test` も一時的な日本語フォルダの画像/動画を生成・読み込み・選択する。
`tools/build/build_one_dir.py --smoke-test` から凍結exeで同じprobeを実行する。
フルWindows VMのPython完全未導入試験と同一視しない。

詳細Inspector/編集Actionは #220、Job Queueは #221。どちらも今回の完了対象ではない。

参考（利用APIの正本）:
- https://docs.python.org/3/library/tkinter.html#threading-model
- https://pillow.readthedocs.io/en/stable/reference/Image.html
- https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html
