"""Deterministic, bounded, bin-aware video frame sampling and replacement."""

import math
import random
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import replace

from comfyui_support_tools.shared.contracts.frame_analysis import FrameDecodeStatus
from comfyui_support_tools.shared.contracts.frame_sampling import (
    FrameCountMode,
    FrameEvaluation,
    FrameSampleRecord,
    FrameSamplingOptions,
    FrameSamplingResult,
    SamplingBin,
)


# {
#   責務: [sample_video_frames: Candidate/Target Kept modeでdeterministic frame candidateを評価・補充する]
#   処理: [1: settings/source binsを検証する 2: stratified initial samplesを評価する 3: drop binからbounded refillする]
#   引数: [source_video_id: manifest source ID, duration: 秒, requested_count: frame count, evaluator: timestampをdecode/filterするcallback, options: seed/mode/budget, bins: optional time/scene/shot bins, clock: budget clock]
#   戻り値: [FrameSamplingResult: kept/attempts/lineage/exhaustionを含むdeterministic結果]
# }
def sample_video_frames(
    source_video_id: str,
    duration: float,
    requested_count: int,
    evaluator: Callable[[float], FrameEvaluation],
    options: FrameSamplingOptions | None = None,
    bins: Sequence[SamplingBin] | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> FrameSamplingResult:
    options = options or FrameSamplingOptions()
    mode = FrameCountMode(options.count_mode)
    if (
        not isinstance(source_video_id, str)
        or not source_video_id.strip()
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("source ID and finite positive duration are required")
    if type(requested_count) is not int or not 1 <= requested_count <= 100_000:
        raise ValueError("requested_count must be in 1..100000")
    if (
        type(options.sampling_seed) is not int
        or type(options.bin_count) is not int
        or not 1 <= options.bin_count <= 1000
        or type(options.max_attempts) is not int
        or not 1 <= options.max_attempts <= 100_000
        or type(options.max_candidate_multiplier) is not int
        or not 1 <= options.max_candidate_multiplier <= 100
        or not math.isfinite(options.max_wall_time_seconds)
        or options.max_wall_time_seconds <= 0
        or not callable(evaluator)
        or not callable(clock)
    ):
        raise ValueError("invalid sampling budget or seed")
    sampling_bins = tuple(bins) if bins is not None else _time_bins(duration, options.bin_count)
    _validate_bins(sampling_bins, duration)
    budget = min(options.max_attempts, requested_count * options.max_candidate_multiplier)
    generator = random.Random(f"{options.sampling_seed}:{source_video_id}")
    started_at = clock()
    attempts: list[FrameSampleRecord] = []
    kept: list[FrameSampleRecord] = []
    seen_kept_frame_ids = set()
    timestamps = _initial_timestamps(requested_count, sampling_bins, generator)
    seen = set(timestamps)
    pending: deque[tuple[SamplingBin, str]] = deque()
    stop_reason = ""

    for timestamp in timestamps[:budget]:
        if _out_of_time(started_at, options.max_wall_time_seconds, clock):
            stop_reason = "max_wall_time"
            break
        sampling_bin = _bin_at(timestamp, sampling_bins)
        record = _evaluate_candidate(
            source_video_id,
            timestamp,
            sampling_bin,
            "initial",
            "",
            len(attempts),
            evaluator,
        )
        record = _reject_duplicate_actual_frame(record, seen_kept_frame_ids)
        attempts.append(record)
        if record.filter_result == "keep":
            kept.append(record)
        elif mode is FrameCountMode.TARGET_KEPT:
            pending.append((sampling_bin, record.candidate_id))
    if len(timestamps) > budget and not stop_reason:
        stop_reason = _budget_reason(options, requested_count)

    if mode is FrameCountMode.TARGET_KEPT:
        draw_limit = min(max(budget * 2, 8), 64)
        while len(kept) < requested_count and pending and len(attempts) < budget:
            if _out_of_time(started_at, options.max_wall_time_seconds, clock):
                stop_reason = "max_wall_time"
                break
            sampling_bin, parent_id = pending.popleft()
            timestamp = _replacement_timestamp(sampling_bin, generator, seen, draw_limit)
            if timestamp is None:
                stop_reason = "no_unique_timestamps"
                break
            seen.add(timestamp)
            record = _evaluate_candidate(
                source_video_id,
                timestamp,
                sampling_bin,
                "replacement",
                parent_id,
                len(attempts),
                evaluator,
            )
            record = _reject_duplicate_actual_frame(record, seen_kept_frame_ids)
            attempts.append(record)
            if record.filter_result == "keep":
                kept.append(record)
            else:
                pending.append((sampling_bin, record.candidate_id))
        if len(kept) >= requested_count:
            stop_reason = "target_reached"
        elif not stop_reason:
            stop_reason = (
                "insufficient_candidates"
                if not pending
                else _budget_reason(options, requested_count)
            )
    elif not stop_reason:
        stop_reason = "candidate_count_complete"

    return FrameSamplingResult(
        source_video_id,
        duration,
        mode,
        requested_count,
        options.sampling_seed,
        options,
        sampling_bins,
        tuple(attempts),
        tuple(kept),
        stop_reason,
    )


# {
#   責務: [_time_bins: 動画durationを均一な隣接time binsへ分割する]
#   処理: [1: bin countをdurationより大きくしない 2: 最後のbinをdurationへ閉じる]
#   引数: [duration: video duration seconds, bin_count: requested bin number]
#   戻り値: [bins: contiguous time ranges]
# }
def _time_bins(duration: float, bin_count: int) -> tuple[SamplingBin, ...]:
    count = min(bin_count, max(1, int(math.ceil(duration))))
    return tuple(
        SamplingBin(
            f"time-{index:04d}",
            duration * index / count,
            duration * (index + 1) / count,
        )
        for index in range(count)
    )


# {
#   責務: [_validate_bins: caller-provided binsがduration全体を連続して覆うことを検証する]
#   処理: [1: empty/duplicate/range errorsを拒否する 2: contiguous partitionと動画終端を検証する]
#   引数: [bins: sampling bins, duration: source duration]
#   戻り値: []
# }
def _validate_bins(bins: tuple[SamplingBin, ...], duration: float) -> None:
    if not bins or len(bins) > 10_000:
        raise ValueError("one or more sampling bins are required")
    if len({item.id for item in bins}) != len(bins):
        raise ValueError("sampling bin IDs must be unique")
    cursor = 0.0
    for item in bins:
        if (
            not item.id
            or not math.isfinite(item.start)
            or not math.isfinite(item.end)
            or item.end <= item.start
            or abs(item.start - cursor) > 1e-9
        ):
            raise ValueError("sampling bins must be contiguous, positive ranges from time zero")
        cursor = item.end
    if abs(cursor - duration) > max(1e-9, duration * 1e-9):
        raise ValueError("sampling bins must cover the full video duration")


# {
#   責務: [_initial_timestamps: binsへ比例配分し均等層化したinitial timestampを作る]
#   処理: [1: bin duration比率でcountをlargest-remainder配分する 2: 各bin内をstratifyしてseeded sampleする 3: timestamp順に並べる]
#   引数: [count: initial candidate count, bins: complete video bins, generator: deterministic random generator]
#   戻り値: [timestamps: repeatable sorted candidate timestamp tuple]
# }
def _initial_timestamps(
    count: int, bins: tuple[SamplingBin, ...], generator: random.Random
) -> tuple[float, ...]:
    total_duration = bins[-1].end
    exact_counts = [count * (item.end - item.start) / total_duration for item in bins]
    allocations = [math.floor(value) for value in exact_counts]
    remaining = count - sum(allocations)
    tie_breakers = [generator.random() for _ in bins]
    priority = sorted(
        range(len(bins)),
        key=lambda index: (-(exact_counts[index] - allocations[index]), tie_breakers[index]),
    )
    for index in priority[:remaining]:
        allocations[index] += 1
    timestamps = []
    for sampling_bin, amount in zip(bins, allocations, strict=True):
        width = sampling_bin.end - sampling_bin.start
        for index in range(amount):
            segment_start = sampling_bin.start + width * index / amount
            segment_end = sampling_bin.start + width * (index + 1) / amount
            timestamps.append(generator.uniform(segment_start, segment_end))
    return tuple(sorted(timestamps))


# {
#   責務: [_bin_at: timestampを含むsampling binを返す]
#   処理: [1: half-open intervalを検索する 2: duration終端のみ最後のbinへ含める]
#   引数: [timestamp: sample time, bins: contiguous bins]
#   戻り値: [sampling_bin: timestampのbin]
# }
def _bin_at(timestamp: float, bins: tuple[SamplingBin, ...]) -> SamplingBin:
    for item in bins:
        if item.start <= timestamp < item.end:
            return item
    if timestamp == bins[-1].end:
        return bins[-1]
    raise ValueError("timestamp is outside sampling bins")


# {
#   責務: [_replacement_timestamp: rejected candidateと同じbin内で未使用timestampをseeded抽出する]
#   処理: [1: bounded回uniform候補を作る 2: 既出を避ける 3: 時間不足時はNoneを返す]
#   引数: [sampling_bin: parent candidate bin, generator: seeded RNG, seen: used timestamp set, draw_limit: 最大乱数試行回数]
#   戻り値: [timestamp: unused replacement timestamp or None]
# }
def _replacement_timestamp(
    sampling_bin: SamplingBin,
    generator: random.Random,
    seen: set[float],
    draw_limit: int,
) -> float | None:
    for _ in range(draw_limit):
        candidate = generator.uniform(sampling_bin.start, sampling_bin.end)
        if candidate not in seen:
            return candidate
    return None


# {
#   責務: [_evaluate_candidate: requested timestampをdecode/filterしmanifest lineage recordへ正規化する]
#   処理: [1: evaluatorを呼ぶ 2: valid frame/filter結果を確認する 3: time/PTS/bin/generation/parentを保存する]
#   引数: [source_video_id: source, timestamp: requested time, sampling_bin: distribution bin, generation: initial/replacement, parent_id: drop lineage, index: sequence, evaluator: decoder/filter adapter]
#   戻り値: [record: attempt manifest record]
# }
def _evaluate_candidate(
    source_video_id: str,
    timestamp: float,
    sampling_bin: SamplingBin,
    generation: str,
    parent_id: str,
    index: int,
    evaluator: Callable[[float], FrameEvaluation],
) -> FrameSampleRecord:
    try:
        evaluation = evaluator(timestamp)
    except Exception as error:
        evaluation = FrameEvaluation(None, False, f"evaluation_failed:{type(error).__name__}")
    if not isinstance(evaluation, FrameEvaluation):
        evaluation = FrameEvaluation(None, False, "invalid_evaluation_result")
    frame = evaluation.frame
    valid = frame is not None and frame.has_pixels and frame.decode_status is FrameDecodeStatus.OK
    if not valid:
        result = evaluation.reason or (
            f"decode:{frame.decode_status.value}" if frame is not None else "decode:missing_frame"
        )
        keep = False
    else:
        keep = bool(evaluation.keep)
        result = "keep" if keep else (evaluation.reason or "filtered")
    return FrameSampleRecord(
        f"sample-{index:08d}",
        source_video_id,
        timestamp,
        frame.actual_timestamp if frame is not None else None,
        frame.pts if frame is not None else None,
        frame.time_base if frame is not None else None,
        sampling_bin.id,
        generation,
        result[:300],
        parent_id,
    )


# {
#   責務: [_reject_duplicate_actual_frame: seekが同じPTS/timeへ解決した重複frameをkeep候補から除く]
#   処理: [1: PTS/time_baseとactual timestamp identityを作る 2: 既kept frameと重なる場合duplicateとして記録する]
#   引数: [record: candidate manifest record, seen_ids: keep済みのactual frame identity set]
#   戻り値: [record: unique candidate、またはduplicate resultへ変更したrecord]
# }
def _reject_duplicate_actual_frame(
    record: FrameSampleRecord,
    seen_ids: set[tuple],
) -> FrameSampleRecord:
    if record.filter_result != "keep":
        return record
    identities = set()
    if record.pts is not None and record.time_base is not None:
        identities.add(("pts", record.pts, record.time_base))
    if record.actual_timestamp is not None:
        identities.add(("time", round(record.actual_timestamp, 6)))
    if identities.intersection(seen_ids):
        return replace(record, filter_result="duplicate_actual_frame")
    seen_ids.update(identities)
    return record


# {
#   責務: [_out_of_time: wall-clock sampling budgetが尽きたかを照会する]
#   処理: [1: monotonic elapsed timeを計算する 2: max durationと比較する]
#   引数: [started_at: initial monotonic time, max_wall_time_seconds: maximum duration, clock: monotonic source]
#   戻り値: [expired: budget exhausted]
# }
def _out_of_time(started_at: float, max_wall_time_seconds: float, clock) -> bool:
    return clock() - started_at >= max_wall_time_seconds


# {
#   責務: [_budget_reason: attempt上限に達した詳細budget理由を決める]
#   処理: [1: max_attemptsとmultiplier capを比較する 2: 先に尽きた上限を返す]
#   引数: [options: sampling options, requested_count: kept/candidate target]
#   戻り値: [reason: max_attemptsまたはmax_candidate_multiplier]
# }
def _budget_reason(options: FrameSamplingOptions, requested_count: int) -> str:
    multiplier_limit = requested_count * options.max_candidate_multiplier
    return (
        "max_attempts" if options.max_attempts <= multiplier_limit else "max_candidate_multiplier"
    )
