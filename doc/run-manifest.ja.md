# Application 共通 Run Manifest

`shared.contracts.run_manifest` は実行 identity と Job ID、lifecycle、input/output reference、resolved settings、seed と実際の random selection、component version、environment、warning/error、candidate decision、repair/retry lineage、user override、再現性 level を持つ versioned immutable record を定義します。artifact 本体は埋め込まず、reference に size、任意の上限付き SHA-256、requested/actual timestamp、PTS、time_base などの media timing を記録できます。

run 開始時に `create_run_manifest_for_job` で既存 `JobSnapshot` と明示設定を結び付け、保存後の path を `JobRuntime.set_manifest_ref` で記録できます。Job を使わない Application は `create_run_manifest` を呼び、終了時に `finish_run_manifest` で terminal status と結果を保存します。`generate_random_seed` は Application が明示的に採用する seed を生成します。乱数を使わない処理に seed を作る必要はありません。`JsonRunManifestStore` は digest 検証付き JSON を atomic 保存します。`JsonLineRunEventStore` は run ごとに writer を一つとして lifecycle/progress record を順序付き append します。project DB や index への adapter は schema を変えず `RunManifestStore` protocol で追加できます。

privacy mode は field ごとに `full`、`hash`、`summary`、`none` を指定します。`settings.prompt` だけ削除して他の設定を再現用に残せます。hash/summary/none の設定は replay を止めます。未指定 field は full 保存となるため、prompt、path、個人情報、大きな workflow payload は各 Application が data policy に従って明示してください。巨大な中間データを自動で埋め込みません。artifact hashing は上限付きで、読取中にファイル差し替えや更新が起きた場合は fingerprint を作らず失敗します。

`manifest_replay_request` は settings が full 保存されている場合に限り、保存済み input/settings/seeds を返します。これは再投入 request であり、bit-exact な出力を保証する表示ではありません。`deterministic`、`best_effort`、`non_deterministic` を明示します。`compare_run_manifests` は field ごとの差分を返します。共通 CLI registration は後続の CLI harness から利用できる `run show`、`run replay`、`run compare` を提供します。schema v0/v1 は Job ID を加える v2 へ additive migration し、未知の将来 version は拒否します。
