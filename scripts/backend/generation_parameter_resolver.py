"""Resolve Random Image generation settings once for each image."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any


class GenerationParameterResolver:
    """Validate and resolve fixed, ranged, and candidate generation settings."""

    def __init__(self, random_source: Any | None = None) -> None:
        self._random = random_source or random.SystemRandom()

    def resolve(self, configuration: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(configuration, Mapping):
            raise ValueError("generation parameter configuration must be an object")
        return {
            "cfg": self._resolve_number(configuration.get("cfg"), "cfg", 0.0, 50.0),
            "steps": self._resolve_integer(configuration.get("steps"), "steps", 1, 150),
            "resolution": self._resolve_resolution(configuration.get("resolution")),
            "sampler": self._resolve_sampler(configuration.get("sampler")),
        }

    def _resolve_number(self, spec: Any, name: str, minimum: float, maximum: float) -> float:
        self._validate_numeric_options(spec, name, minimum, maximum)
        value = self._resolve_scalar(spec, name, allow_range=True, allow_candidates=True)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must resolve to a finite number")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return float(value)

    def _resolve_integer(self, spec: Any, name: str, minimum: int, maximum: int) -> int:
        self._validate_integer_options(spec, name, minimum, maximum)
        value = self._resolve_scalar(spec, name, allow_range=True, allow_candidates=True)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must resolve to an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    def _resolve_resolution(self, spec: Any) -> dict[str, int]:
        if isinstance(spec, Mapping) and spec.get("mode") == "candidate":
            for candidate in self._candidate_values(spec, "resolution"):
                self._validate_resolution_value(candidate)
        value = self._resolve_scalar(spec, "resolution", allow_range=False, allow_candidates=True)
        return self._validate_resolution_value(value)

    def _validate_resolution_value(self, value: Any) -> dict[str, int]:
        if not isinstance(value, Mapping):
            raise ValueError("resolution value must contain width and height")
        width = self._dimension(value.get("width"), "width")
        height = self._dimension(value.get("height"), "height")
        return {"width": width, "height": height}

    @staticmethod
    def _dimension(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= 4096 or value % 8:
            raise ValueError(f"{name} must be a multiple of 8 between 64 and 4096")
        return value

    def _resolve_sampler(self, spec: Any) -> str:
        if isinstance(spec, Mapping) and spec.get("mode") == "candidate":
            for candidate in self._candidate_values(spec, "sampler"):
                if not isinstance(candidate, str) or not candidate.strip():
                    raise ValueError("sampler candidates must contain non-empty text")
        value = self._resolve_scalar(spec, "sampler", allow_range=False, allow_candidates=True)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("sampler must resolve to non-empty text")
        return value.strip()

    def _validate_numeric_options(self, spec: Any, name: str, minimum: float, maximum: float) -> None:
        if not isinstance(spec, Mapping):
            return
        if spec.get("mode") == "range":
            options = (spec.get("min"), spec.get("max"))
            self._validate_numeric_candidates(options, name, minimum, maximum)
            if options[0] > options[1]:
                raise ValueError(f"{name} range minimum exceeds maximum")
        if spec.get("mode") == "candidate":
            for value in self._candidate_values(spec, name):
                self._validate_numeric_candidates((value,), name, minimum, maximum)

    def _validate_integer_options(self, spec: Any, name: str, minimum: int, maximum: int) -> None:
        if not isinstance(spec, Mapping):
            return
        if spec.get("mode") == "range":
            options = (spec.get("min"), spec.get("max"))
            for value in options:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{name} range endpoints must be integers")
            if not minimum <= options[0] <= maximum or not minimum <= options[1] <= maximum:
                raise ValueError(f"{name} range endpoints must be between {minimum} and {maximum}")
            if options[0] > options[1]:
                raise ValueError(f"{name} range minimum exceeds maximum")
        if spec.get("mode") == "candidate":
            for value in self._candidate_values(spec, name):
                if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                    raise ValueError(f"{name} candidates must be integers between {minimum} and {maximum}")

    @staticmethod
    def _validate_numeric_candidates(values, name: str, minimum: float, maximum: float) -> None:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} range values must be finite numbers")
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite or not minimum <= value <= maximum:
                raise ValueError(f"{name} values must be finite numbers between {minimum} and {maximum}")

    @staticmethod
    def _candidate_values(spec: Mapping[str, Any], name: str) -> Sequence[Any]:
        values = spec.get("values")
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ValueError(f"{name} candidates must be a non-empty list")
        return values

    def _resolve_scalar(
        self,
        spec: Any,
        name: str,
        *,
        allow_range: bool,
        allow_candidates: bool,
    ) -> Any:
        if not isinstance(spec, Mapping):
            raise ValueError(f"{name} configuration must be an object")
        mode = spec.get("mode")
        if mode == "fixed":
            return spec.get("value")
        if mode == "range" and allow_range:
            lower = spec.get("min")
            upper = spec.get("max")
            if isinstance(lower, bool) or isinstance(upper, bool):
                raise ValueError(f"{name} range endpoints are invalid")
            if isinstance(lower, int) and isinstance(upper, int):
                if lower > upper:
                    raise ValueError(f"{name} range minimum exceeds maximum")
                return self._random.randint(lower, upper)
            if not all(isinstance(item, (int, float)) and math.isfinite(item) for item in (lower, upper)):
                raise ValueError(f"{name} range endpoints must be finite numbers")
            if lower > upper:
                raise ValueError(f"{name} range minimum exceeds maximum")
            return self._random.uniform(float(lower), float(upper))
        if mode == "candidate" and allow_candidates:
            values = self._candidate_values(spec, name)
            return self._random.choice(values)
        allowed = ["fixed"]
        if allow_range:
            allowed.append("range")
        if allow_candidates:
            allowed.append("candidate")
        raise ValueError(f"{name} mode must be one of: {', '.join(allowed)}")
