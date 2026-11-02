# Deterministic video frame sampling

`sample_video_frames` accepts a video ID, duration, target count, a bounded
decoder/filter evaluator, and `FrameSamplingOptions`. It returns all attempts
and kept frames in `FrameSamplingResult`. The result retains the exact options
and bin boundaries alongside the sampled timestamps so applications can persist
and replay the sampling plan.

`candidate_count` evaluates exactly the requested number of initial candidates
when budgets permit. Filtered candidates remain in `attempts`, and no refill is
performed. `target_kept` distributes initial candidates over time bins (or
caller-supplied contiguous scene/shot bins), then requests replacements from
the same bin as each rejected candidate until the target is met or a budget is
exhausted. Seeded largest-remainder allocation avoids always selecting the
first bin when the requested count is smaller than the bin count.

Each attempt records source video ID, requested and actual timestamps, PTS and
time base, bin ID, `initial`/`replacement` generation, filter result, and parent
candidate ID for replacement lineage. `FrameAnalysisInput` decode errors are
rejected before the user filter can keep them.

The loop is bounded by `max_attempts`, `max_candidate_multiplier`, and
`max_wall_time_seconds`. Results report `target_reached`,
`candidate_count_complete`, `max_attempts`, `max_candidate_multiplier`,
`max_wall_time`, `no_unique_timestamps`, or `insufficient_candidates`.
Evaluators must also enforce their decoder/network timeout because a synchronous
callback cannot be interrupted safely while it is running.

Scene/shot-aware refill is supplied through contiguous `SamplingBin` ranges;
the sampling core does not run scene detection itself. This lets the Video
Capability and low-information filter supply their own bins while sharing the
same deterministic plan and lineage contract.
