# 決定的な Video Frame Sampling

`sample_video_frames` はvideo ID、duration、指定枚数、timeoutを持つdecoder/filter
evaluator、`FrameSamplingOptions` を受け取ります。全attemptと最終keepを
`FrameSamplingResult` に返します。結果はoptionsとbin boundariesも保持するため、Applicationは
sampling timestamp manifestとして保存し、同じplanを再現できます。

`candidate_count` はbudget内で指定数のinitial candidateを評価します。filterで落ちた候補も
`attempts` に残し、replacementはしません。`target_kept` はtime binまたは呼び出し元が渡した
連続scene/shot binへinitial candidateを配分し、target枚数になるかbudgetが尽きるまで、dropした
candidateと同じbinからreplacementを要求します。requested countがbin数より少ない場合も、
seed付きlargest-remainder配分で先頭binへ固定偏重しません。

各attemptにはsource video ID、requested/actual timestamp、PTS/time_base、bin ID、
`initial`/`replacement` generation、filter結果、replacement元candidate IDを記録します。
`FrameAnalysisInput` がdecode errorなら、filterへkeep判定を委ねずdropします。

処理回数は `max_attempts`、`max_candidate_multiplier`、`max_wall_time_seconds` で制限します。
終了理由は `target_reached`、`candidate_count_complete`、`max_attempts`、
`max_candidate_multiplier`、`max_wall_time`、`no_unique_timestamps`、
`insufficient_candidates` のいずれかです。同期callbackの実行中はloopから強制停止できないため、
evaluator側もdecoder/network timeoutを設定してください。

scene/shot binは連続した `SamplingBin` rangesとして渡します。sampling core自身はscene検出を
行わず、Video Capabilityやlow-information filterがbinを用意して同じ決定的planとlineage contract
を使えるようにします。
