# Touka 実写 Hard-case Loop

`shared.hard_case_loop` は、実画像を外部送信せずに失敗例と選択結果を蓄積し、hard-case の分類、代表例選択、active-learning 用参照一覧、feedback calibration、固定 regression set の比較へつなぐローカル機能です。

## 記録と feedback

`HardCaseRecord` (`touka-hard-case.v1`) は入力 SHA-256、ローカルパス参照、画像/動画/burst のメタデータ、材質と条件、候補 raw score / confidence、confidence map 参照、選択/拒否/ユーザー希望、失敗タグ、runtime / VRAM、model/config、任意 GT / weak label、multi-axis feature を保持します。画像 byte 自体はrecordへ複製しません。`HardCaseStore` は caller が選ぶ SQLite ファイルに versioned JSON record を保存します。`record_feedback` でユーザー希望候補と拒否候補を明示して保存できます。

## Hardness、cluster、sample

`extract_hard_case_features` は confidence map から low-confidence area ratio を算出し、候補 score の disagreement と residual / temporal / artifact 指標を別軸で保持します。現在のクラスタリングは feature centroid 距離と material / failure tag の一致を使う説明可能な deterministic baseline で、画像 embedding や学習済み clustering model ではありません。`cluster_hard_cases` は cluster ごとに centroid に近い代表recordを返し、`select_active_learning_samples` は rare tag/material、候補間 disagreement、hardness、ユーザーが拒否した高 confidence 候補を優先します。

## Calibration と regression

`calibrate_confidence` は明示的 feedback のある selected candidate のみをラベル化し、ECE と reliability bins、high-confidence error ID を返します。未ラベル record は正解として数えず、raw scoreを確率とみなしません。`in_regression_set` を付けた record を `run_regression_set` に渡すと、注入 evaluator が同じローカル参照を model/config ごとに再評価し、user-preferred candidate の Top-1/3/5 と catastrophic failure 数を比較します。`compare_model_configs` は複数の version/config を同じ固定集合へ適用します。

`export_active_learning_manifest` は入力 hash、ローカル参照、metric、feedbackのみをJSONへ出し、画像をコピー・uploadしません。実写データセット、埋め込みモデル、学習器、自動Touka candidate hook は同梱していません。実データの regression set はユーザーがローカル記録から選んで固定します。

確認: `python -m unittest tests.test_hard_case_loop`。
