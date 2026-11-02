# 共通 Resource Budget と backpressure

`shared.resource_budget` は注入可能な `ResourceBudgetManager` を提供します。Application の composition root は `GLOBAL_RESOURCE_BUDGET_MANAGER` を共用し、Application 間で reservation を共有してください。run、Application、global の順に具体的な profile を解決し、最後に safe default を使います。global 値は Application 間で共有する上限として維持します。より狭い profile は上限を下げられますが、run の要求が global 上限を超えることはできません。resource lease は context manager として速やかに解放してください。

`BoundedResourceStage` は stage ごとに worker 数と有限 queue を持ちます。ある stage の出力を次の stage へ渡せます。downstream queue が満杯になると worker が待ち、backpressure が upstream producer まで伝わります。各 stage は CPU thread/process、GPU job、disk、network、external API concurrency を個別に制御できます。cancel は新規投入を止めて pending item を破棄します。実行中 handler の停止は adapter 境界で cancellation token を確認してください。`MemoryError` 後の縮退実行は設定 callback を一度だけ試します。failure は集計し、optional error hook に通知します。

`shared.retry_policy.external_api_backoff` は Retry-After を尊重する上限付き exponential delay を計算します。`shared.versioned_cache.BoundedVersionedCache` は明示的 schema version key、LRU 上限、clear/eviction を提供します。cache value の schema は各 domain Application が管理し、表示 threshold のように結果を変えない値を key へ含めないでください。

既存の JobRuntime は job 全体の lifecycle と priority の責務を維持します。resource stage にはその job の run ID、cancellation event、priority、resolved run profile を渡し、別の whole-job scheduler を作らずに共有 budget を適用してください。CLI adapter は `add_resource_budget_arguments` で共通 flags を登録し、`resolve_resource_budget_options` で optional override へ変換します。GUI 設定も同じ `ResourceBudgetOverride` contract へ対応づけ、どちらも profile を shared manager へ渡します。
