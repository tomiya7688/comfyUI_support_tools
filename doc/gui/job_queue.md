# Shared Job Queue — #221

`KadokaTools.exe --new-ui` の下部 **Jobs** パネルは、Main GUI内の長時間処理を
同じGUI非依存Job modelで表示する。

## 現在Job化される処理

- `media_scan`: #219のフォルダ走査。総件数を事前に列挙しないため進捗率は不定、検出済み件数をmessage/logへ表示する。
- `tagger_probe`: #220のTaggerモデル一覧/接続確認。
- `tagger_tag`: #220の1〜60画像Tag batch。処理済み件数から0〜100%を表示する。

サムネイル/Inspector previewのような短い表示補助処理はJobにしない。今後ComfyUI、動画、LoRA等は同じJob契約と明示adapterへ接続する。

## 状態と契約

`shared/contracts/job_contracts.py` の immutable `JobSnapshot` がUI/Process/Dataを越える契約。

- state: `queued / preparing / running / pausing / paused / cancelling / cancelled / resuming / retrying / done / failed / interrupted`（旧adapterの`error`も読み込める）
- progress: `0..1` または総量不明時 `None`
- created / started / finished timestamp
- action / kind / source media IDsと表示名
- compact log（最大50行、各400文字）
- error
- `backend_job_id`: ComfyUI等の外部job/prompt IDを保持する予約field
- `register_cancel_handler(job_id, handler, capability)`: process/backend adapterが停止callbackを登録する。通常停止とGUI終了時にJob IDとともに呼ばれ、callback例外はJob logへ記録される。既存名`register_backend_cancel_handler`も互換で残す
- `cancel_capability`: cooperative / process / backend / noneを表す。noneのJobは停止ボタンが無効
- `checkpoint_capability / checkpoint_ref`: none / stage / item / nativeと再開位置。`pause -> checkpoint -> wait_if_paused -> resume`で同じruntime内のworkerを止めて再開する
- `shutdown_policy`: cancel / finish_current_item / checkpoint_and_stop / detachをJob単位で指定する
- `operation_id / manifest_ref`: Run Manifestとの紐付け、retry idempotency key
- completed / pending / failed item IDsと`artifact_refs`: partial resultの状態参照
- `retry_of / retryable`: 登録handlerでmanifestからchild Jobを作る。親Jobと同じoperation ID、およびretry_ofを検証し、二重retry要求には既存childを返す

履歴は最大100件で、古いterminal Jobから破棄する。`create_job_runtime()` はSQLite snapshotをOS state directoryへ保存する。既定はWindows `%LOCALAPPDATA%`、Unix系 `$XDG_STATE_HOME`（未指定時`~/.local/state`）内の`comfyui_support_tools/jobs.sqlite3`。設定用`COMFYUI_SUPPORT_TOOLS_STATE_DIR`で保存先を変更できる。Job入力payloadは複製せず、再開に必要な内容はRun Manifestが保持し、snapshotにはmanifest/checkpoint参照だけを保存する。

## 同時実行とCancel

共有 `JobRuntime(max_concurrent=2)` がData層IO workerの開始slotを管理する。3件目以降はqueuedのまま待つ。現在のMedia ScanとTag処理も同じ上限を共有する。

- queuedを停止: worker開始前に`cancelled`
- runningを停止: cancel Eventを通知。Media Scanは走査loopで協調停止、Tag HTTPは現在のHTTP応答/timeout後に次の画像へ進まず停止
- ネイティブ/OS/HTTP呼び出しを強制killする契約ではない
- GUI終了: queuedをcancelled、runningへ停止Eventを通知し、完了待ちでGUI終了を止めない
- `checkpoint_and_stop`: 次のcheckpointでpausedとして保存し、プロセス終了後もmanifest/checkpoint参照を残す。`detach`は外部backendへ停止を要求せず、復元時はinterruptedになる
- 既に外部backendへ受理された処理は、adapterがbackend ID単位の停止callbackを登録すればサーバー側へ停止要求をdispatchできる
- callbackはUIを止めないよう、非blockingでbackend停止要求をqueueへ登録する。HTTP通信そのものはadapter worker側で実行する

## 画面

Jobs tab:
- 状態、進捗、Action、Source、開始時刻、短いmessage
- 選択したJobのID、backend_job_id、完了時刻、compact log/error
- queued/running Jobの「停止」
- pause可能なJobに「一時停止 / 再開」、retryable Jobに「再実行」を表示する。再起動後のresumeはkind別handlerがmanifestからpayloadを復元してworkerを起動する

UI Log tabは従来どおり画面操作ログ。Job logとは分離する。

## Architecture

実処理は既存Data Processing（Media Scan / Tagger HTTP）が担当し、同じData層 `JobRuntime` へ状態だけ報告する。UIは次だけを参照する。

`JobQueuePanel -> UI Commander -> UI Messenger -> Process Messenger -> Process Commander -> Data Messenger -> Data Commander -> JobRuntime`

Job UIがTagger/Media Scanの実装moduleを直接importすることはない。別Application内部・Python/venv/module path共有にも依存しない。

## Validation

- `tests/test_job_runtime.py`: lifecycle、durable restart/resume、item checkpoint/pause、idempotent retry、backend cancellation、shutdown policy、履歴上限、Media Scan + Tag系の共有runtime
- `tests/test_job_queue_ui.py`: 複数Job、progress/error/log、cancel、backend_job_id表示
- Windows full completion gate / UPD / app-boundary
- onedir `--shell-smoke-test`: Media Scan、Tagger probe、Tag batchの3 kindが同じJobs履歴へterminal stateで表示されることを確認

localhost fake TaggerはHTTP契約試験でありAI推論精度の試験ではない。完全なPython未導入Windows VM検証とも区別する。
