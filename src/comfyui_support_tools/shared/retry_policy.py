"""Bounded retry timing policies for external APIs."""

import math


# {
#   責務: [external_api_backoff: bounded exponential backoffを算出する]
#   処理: [1: retry attempt/boundsを検証する 2: Retry-Afterを尊重し上限へclampする]
#   引数: [attempt: 1-based retry index, base_seconds: initial delay, maximum_seconds: cap, retry_after_seconds: server hint]
#   戻り値: [delay: bounded sleep seconds]
# }
def external_api_backoff(
    attempt: int,
    base_seconds: float = 0.5,
    maximum_seconds: float = 30.0,
    retry_after_seconds: float | None = None,
) -> float:
    if type(attempt) is not int or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    delays = (base_seconds, maximum_seconds) + (
        () if retry_after_seconds is None else (retry_after_seconds,)
    )
    if any(
        isinstance(delay, bool)
        or not isinstance(delay, (int, float))
        or not math.isfinite(delay)
        or delay < 0
        for delay in delays
    ):
        raise ValueError("backoff bounds and Retry-After must be finite and nonnegative")
    if retry_after_seconds is not None:
        return min(maximum_seconds, retry_after_seconds)
    return min(maximum_seconds, base_seconds * (2 ** min(attempt - 1, 30)))
