"""Resolve Random Image generation settings once for each image."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any
from src.comfyui_support_tools.shared.contracts.resolved_generation_parameters import (
    ResolvedGenerationParameters,
)


# {
#   責務: [GenerationParameterResolver: generation settingsをvalidateし、1画像分の値へresolveする]
#   処理: [fixed, range, candidate modesを検証してnumeric/resolution/sampler valuesを選択する]
#   フィールド: [random source]
# }
class GenerationParameterResolver:
    """Validate and resolve fixed, ranged, and candidate generation settings."""

    # {
    #   責務: [__init__: random selection用sourceを保存する]
    #   処理: [injected random sourceを使い、未指定時はSystemRandomを生成する]
    #   引数: [random_source]
    #   戻り値: [None]
    # }
    def __init__(self, random_source: Any | None = None) -> None:
        self._random = random_source or random.SystemRandom()

    # {
    #   責務: [resolve: 設定候補を検証し, 1枚分の確定済み型付き生成値を作る]
    #   処理: [CFG, step数, 解像度, samplerを抽選または固定値で解決する]
    #   引数: [self: resolver, configuration: GUI非依存の候補設定]
    #   戻り値: [ResolvedGenerationParameters: バックエンドへ渡す確定値]
    # }
    def resolve(self, configuration: Mapping[str, Any]) -> ResolvedGenerationParameters:
        if not isinstance(configuration, Mapping):
            raise ValueError("generation parameter configuration must be an object")
        cfg = self._resolve_number(configuration.get("cfg"), "cfg", 0.0, 50.0)
        steps = self._resolve_integer(configuration.get("steps"), "steps", 1, 150)
        resolution = self._resolve_resolution(configuration.get("resolution"))
        sampler = self._resolve_sampler(configuration.get("sampler"))
        return ResolvedGenerationParameters(
            cfg,
            steps,
            resolution["width"],
            resolution["height"],
            sampler,
        )

    # {
    #   責務: [_resolve_number: numeric settingをvalidate and resolveしてfloatへ返す]
    #   処理: [range/candidatesを検証し有限値とboundsを確認する]
    #   引数: [spec, name, minimum, maximum]
    #   戻り値: [float]
    # }
    def _resolve_number(self, spec: Any, name: str, minimum: float, maximum: float) -> float:
        self._validate_numeric_options(spec, name, minimum, maximum)
        value = self._resolve_scalar(spec, name, allow_range=True, allow_candidates=True)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must resolve to a finite number")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return float(value)

    # {
    #   責務: [_resolve_integer: integer settingをvalidate and resolveする]
    #   処理: [range/candidatesとinteger type/boundsを検証する]
    #   引数: [spec, name, minimum, maximum]
    #   戻り値: [int]
    # }
    def _resolve_integer(self, spec: Any, name: str, minimum: int, maximum: int) -> int:
        self._validate_integer_options(spec, name, minimum, maximum)
        value = self._resolve_scalar(spec, name, allow_range=True, allow_candidates=True)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must resolve to an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    # {
    #   責務: [_resolve_resolution: resolution specを選択しwidth/height mappingへresolveする]
    #   処理: [candidate resolutionsを検証しscalar configurationを解決する]
    #   引数: [spec]
    #   戻り値: [dict[str, int]]
    # }
    def _resolve_resolution(self, spec: Any) -> dict[str, int]:
        if isinstance(spec, Mapping) and spec.get("mode") == "candidate":
            for candidate in self._candidate_values(spec, "resolution"):
                self._validate_resolution_value(candidate)
        value = self._resolve_scalar(spec, "resolution", allow_range=False, allow_candidates=True)
        return self._validate_resolution_value(value)

    # {
    #   責務: [_validate_resolution_value: resolution valueのwidth and height dimensionsを検証する]
    #   処理: [mapping shapeと各8-pixel-aligned dimension boundsを確認する]
    #   引数: [value]
    #   戻り値: [dict[str, int]]
    # }
    def _validate_resolution_value(self, value: Any) -> dict[str, int]:
        if not isinstance(value, Mapping):
            raise ValueError("resolution value must contain width and height")
        width = self._dimension(value.get("width"), "width")
        height = self._dimension(value.get("height"), "height")
        return {"width": width, "height": height}

    # {
    #   責務: [_dimension: dimension valueを許容されるmultiple-of-eight integerに検証する]
    #   処理: [bool/non-int, range, and alignment errorsを拒否する]
    #   引数: [value, name]
    #   戻り値: [int]
    # }
    @staticmethod
    def _dimension(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= 4096 or value % 8:
            raise ValueError(f"{name} must be a multiple of 8 between 64 and 4096")
        return value

    # {
    #   責務: [_resolve_sampler: sampler configurationからnon-empty nameをresolveする]
    #   処理: [candidate namesを検証し選択結果をtrimする]
    #   引数: [spec]
    #   戻り値: [str]
    # }
    def _resolve_sampler(self, spec: Any) -> str:
        if isinstance(spec, Mapping) and spec.get("mode") == "candidate":
            for candidate in self._candidate_values(spec, "sampler"):
                if not isinstance(candidate, str) or not candidate.strip():
                    raise ValueError("sampler candidates must contain non-empty text")
        value = self._resolve_scalar(spec, "sampler", allow_range=False, allow_candidates=True)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("sampler must resolve to non-empty text")
        return value.strip()

    # {
    #   責務: [_validate_numeric_options: numeric range/candidate optionsをbounds and finitenessに検証する]
    #   処理: [mode-specific valuesをcandidate validatorへ渡しrange orderを確認する]
    #   引数: [spec, name, minimum, maximum]
    #   戻り値: [None]
    # }
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

    # {
    #   責務: [_validate_integer_options: integer range/candidate valuesのtype, order and boundsを検証する]
    #   処理: [range endpoints and each candidateをstrict integerとして確認する]
    #   引数: [spec, name, minimum, maximum]
    #   戻り値: [None]
    # }
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

    # {
    #   責務: [_validate_numeric_candidates: numeric candidate valuesがfinite and boundedか検証する]
    #   処理: [bool/non-number, overflow, non-finite, and bounds errorsを拒否する]
    #   引数: [values, name, minimum, maximum]
    #   戻り値: [None]
    # }
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

    # {
    #   責務: [_candidate_values: configurationからnon-empty candidate sequenceを取得する]
    #   処理: [string/bytes and non-sequence/empty valuesを拒否する]
    #   引数: [spec, name]
    #   戻り値: [Sequence[Any]]
    # }
    @staticmethod
    def _candidate_values(spec: Mapping[str, Any], name: str) -> Sequence[Any]:
        values = spec.get("values")
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ValueError(f"{name} candidates must be a non-empty list")
        return values

    # {
    #   責務: [_resolve_scalar: fixed, range, or candidate scalar configurationを解決する]
    #   処理: [mode permissionを確認しrandom sourceでvalueを選択する]
    #   引数: [spec, name, allow_range, allow_candidates]
    #   戻り値: [Any]
    # }
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
