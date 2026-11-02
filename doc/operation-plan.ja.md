# Operation plan 共通契約

`shared.contracts.operation_plan` は GUI と CLI が共用する immutable な実行計画を定義します。機能 adapter は入力を解析し、source snapshot、提案 action、理由、conflict、resource 見積り、destination、件数、settings digest を含む `OperationPlan` を作成します。Apply では同じ decision builder を `apply_operation_plan` に渡し、変更前に再計算した提案と保存済み plan を比較します。

`capture_source_snapshot` は path identity と metadata を記録し、8 MiB 以下の通常ファイルには SHA-256 も記録します。それより大きいファイルでは size、更新時刻、mode、device、inode を使います。より強い保証が必要な adapter は domain 固有の content fingerprint を plan settings に含めてください。source/settings の変更と未解決 conflict がある場合は Apply を止めます。delete、remove、overwrite、replace、move、rename、高 risk、review 指定 action には明示的な確認が必要です。個々の filesystem mutation を atomic に実行し、可能な場合は rollback callback を提供する責任は executor にあります。

`preview_operation_plan` は affected/skipped/review の集計と理由別件数を常に返します。上限付き sample は high-risk、理由別代表、seed 固定のランダム例の順で選びます。JSON manifest は integrity digest を含み、共通 atomic artifact writer で保存します。この digest は偶発的な破損検出用で、署名や認可 token ではありません。

`add_operation_cli_arguments` と `resolve_operation_cli_options` は `--dry-run`、`--apply-plan`、`--manifest-only`、`--plan-out`、`--preview-sample` の共通 mode parsing を提供します。各 application はこれらを domain 固有 planner、出力形式、mutation adapter へ接続します。dataset sort と filter は固有の判断ロジックを維持しながら、この共通契約へ移行できます。
