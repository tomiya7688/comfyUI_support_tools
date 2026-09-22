# Workspace Shell (Issue #218)

## 起動 / Launch

既存GUIは引き続き既定です。新Shellは明示的に選択します。

```bat
KadokaTools.exe --new-ui
```

開発用Python環境では以下を使用します。配布版にPythonのインストールは不要です。

```bash
python tabbed_tools_gui.py --new-ui
```

`--new-ui` を付けなければ既存GUIが開きます。新Shellの「旧UIを開く」、または
移行ツールの選択で旧画面へ切り替わります。旧画面下部の「Workspace (新GUI)へ戻る」で
戻れます。同じMain GUI Applicationの画面切替であり、別アプリのmoduleやPythonを起動しません。
同時に2個のTkルートを運用せず、前の画面を閉じて次のevent loopを開始します。

## 今回実装した範囲

- 上部メニュー、クイック操作、Backend API状態表示枠
- 左Library: All / Images / Videos / Dataset / Generated / Favorites / Recent
- 中央Browser、右Inspector、下部Jobs/Logの配置
- 「表示」メニューからLibrary / Inspector / Jobsを個別に折り畳み・再表示
- ペイン境界のドラッグによるリサイズ
- 既存30ツールのカテゴリ・名前検索（Ctrl+Fで検索へ移動）と旧UIへの導線
- Recent: 同一起動セッションで開く操作を行った旧ツール、最新順・重複なし・最大12件
- 空の検索結果、未選択、未使用Recentの表示

画面の表示だけでバックエンドを起動・接続しません。Backend APIは「未確認」と表示します。
接続確認は既存ツール側を使用してください。状態表示をオンラインと偽装しません。

## 未実装 / Follow-up

この段階ではLibrary選択は画面状態の切替のみです。画像一覧/フォルダ走査/お気に入り媒体は
#219、メディア選択連動Inspectorは #220、実Job Queueは #221 に属します。
下部ログは画面操作ログであり、ジョブ実行や完了件数は生成しません。
Recentや検索条件はディスクへ保存せず、アプリ終了でリセットされます。
既存全Tabの処理を新UIへ移植したわけではありません。

## Architecture / Extension points

UI widgets -> UI Commander -> UI Messenger -> Process Messenger -> Process Commander
-> Navigation Processing で操作を処理します。UIの検索文字列/ウィジェットはUI層、
検索・最近使用順・有効IDの判定はProcess層にあります。Shellは外部Applicationの内部moduleを
importせず、旧UI互換コードは製品entrypointだけに閉じ込めています。

`scripts/tab_catalog.py` は旧Tab名・ID・カテゴリだけを持つ移行用メタデータです。
既存 `scripts/app.py` との順序・IDの一致をASTテストで検証します。
新しいメディア機能は旧Tabを増設せず #219/#220 のBrowser/Actionへ追加してください。

## Validation

```bash
python -m unittest tests.test_workspace_shell -v
python tools/completion/completion_gate.py
python tools/build/build_one_dir.py --smoke-test
```

GUIテストはWindows CIで実際のTkを作成して実行します。Linuxでは `xvfb-run -a` 等の
ディスプレイが必要です。画面のないLinuxだけGUIテストをskipし、モデルテストは実行します。

凍結exeは旧UI import、新UI import、実Tk Shell作成・ナビゲーション・折り畳みを検証します。
起動ディレクトリは配布フォルダ外の日本語/空白付き一時フォルダとし、PYTHONPATH/PYTHONHOMEを
除去します。WindowsではPATHもOSディレクトリだけに縮めます。
これは限定した環境隔離smoke testであり、Python未導入の完全クリーンVM検証そのものではありません。
