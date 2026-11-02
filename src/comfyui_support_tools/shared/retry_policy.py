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
    if (
        not math.isfinite(base_seconds)
        or not math.isfinite(maximum_seconds)
        or base_seconds < 0
        or maximum_seconds < 0
        or (
            retry_after_seconds is not None
            and (not math.isfinite(retry_after_seconds) or retry_after_seconds < 0)
        )
    ):
        raise ValueError("backoff bounds and Retry-After must be finite and nonnegative")
    hinted = retry_after_seconds or 0.0
    return min(maximum_seconds, hinted or base_seconds * (2 ** min(attempt - 1, 30)))
