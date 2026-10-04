"""Resolve Random Image generation settings once for each image."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any


# {
# 責務: [GenerationParameterResolver: 固定・範囲・候補形式の生成設定を検証して確定する]
# フィールド: [_random: 範囲・候補から値を選択するrandom source]
# 処理: [1: 各設定modeを検証する, 2: 選択値を範囲と型に照らして検査する,
# 3: backendへ渡すscalar値を返す]
# }
class GenerationParameterResolver:
    """Validate and resolve fixed, ranged, and candidate generation settings."""

    # {
    # 責務: [__init__: 値選択に使うrandom sourceを初期化する]
    # 処理: [1: 注入値がなければSystemRandomを利用する]
    # 引数: [random_source: 任意のchoice・randint・uniform提供元]
    # 戻り値: []
    # }
    def __init__(self, random_source: Any | None = None) -> None:
        self._random = random_source or random.SystemRandom()

    # {
    # 責務: [resolve: cfg・steps・resolution・sampler設定を検証して実値へ解決する]
    # 処理: [1: configuration形式を検証する, 2: 各設定を種別別resolverへ渡す,
    # 3: backend要求用dictionaryを返す]
    # 引数: [configuration: mode別生成parameter設定]
    # 戻り値: [確定したcfg・steps・resolution・sampler値]
    # }
    def resolve(self, configuration: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(configuration, Mapping):
            raise ValueError("generation parameter configuration must be an object")
        return {
            "cfg": self._resolve_number(configuration.get("cfg"), "cfg", 0.0, 50.0),
            "steps": self._resolve_integer(configuration.get("steps"), "steps", 1, 150),
            "resolution": self._resolve_resolution(configuration.get("resolution")),
            "sampler": self._resolve_sampler(configuration.get("sampler")),
        }

    # {
    # 責務: [_resolve_number: 数値設定をmodeから実数へ解決し境界を検証する]
    # 処理: [1: range・candidate値を検査する, 2: 値を選ぶ, 3: 有限値と上下限を確認する]
    # 引数: [spec: 数値parameter設定, name: 設定名, minimum: 許容下限, maximum: 許容上限]
    # 戻り値: [境界内のfloat値]
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
    # 責務: [_resolve_integer: 整数設定をmodeから整数へ解決し境界を検証する]
    # 処理: [1: range・candidate値を検査する, 2: 値を選ぶ, 3: 整数型と上下限を確認する]
    # 引数: [spec: 整数parameter設定, name: 設定名, minimum: 許容下限, maximum: 許容上限]
    # 戻り値: [境界内のint値]
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
    # 責務: [_resolve_resolution: 解像度設定からwidth・heightを選んで検証する]
    # 処理: [1: candidate全件の形状を検証する, 2: 解像度値を選ぶ, 3: dimension条件を確認する]
    # 引数: [spec: 固定またはcandidate解像度設定]
    # 戻り値: [width・heightを持つ解像度dictionary]
    # }
    def _resolve_resolution(self, spec: Any) -> dict[str, int]:
        if isinstance(spec, Mapping) and spec.get("mode") == "candidate":
            for candidate in self._candidate_values(spec, "resolution"):
                self._validate_resolution_value(candidate)
        value = self._resolve_scalar(spec, "resolution", allow_range=False, allow_candidates=True)
        return self._validate_resolution_value(value)

    # {
    # 責務: [_validate_resolution_value: 解像度mapping内の2 dimensionを検証する]
    # 処理: [1: width・heightを整数制約で検査する, 2: 正規化dictionaryを返す]
    # 引数: [value: width・heightを含む解像度候補]
    # 戻り値: [検証済みwidth・height]
    # }
    def _validate_resolution_value(self, value: Any) -> dict[str, int]:
        if not isinstance(value, Mapping):
            raise ValueError("resolution value must contain width and height")
        width = self._dimension(value.get("width"), "width")
        height = self._dimension(value.get("height"), "height")
        return {"width": width, "height": height}

    # {
    # 責務: [_dimension: 画像dimensionの型・範囲・8px alignmentを検証する]
    # 処理: [1: boolや非整数を拒否する, 2: 64から4096の8倍数か確認する]
    # 引数: [value: 検証するdimension, name: error用のparameter名]
    # 戻り値: [検証済みdimension]
    # }
    @staticmethod
    def _dimension(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= 4096 or value % 8:
            raise ValueError(f"{name} must be a multiple of 8 between 64 and 4096")
        return value

    # {
    # 責務: [_resolve_sampler: 固定または候補sampler設定からsampler名を選ぶ]
    # 処理: [1: candidate全件がnon-empty textか検証する, 2: 値を選び空白を整える]
    # 引数: [spec: sampler設定]
    # 戻り値: [空白を除いたsampler名]
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
    # 責務: [_validate_numeric_options: 数値range・candidateの各候補値を先に検査する]
    # 処理: [1: range endpointの型・有限性・範囲・順序を検証する,
    # 2: candidate値ごとに同じ境界を確認する]
    # 引数: [spec: 数値設定, name: 設定名, minimum: 許容下限, maximum: 許容上限]
    # 戻り値: []
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
    # 責務: [_validate_integer_options: 整数range・candidateの型と境界を検証する]
    # 処理: [1: range endpointの整数型・順序・上下限を確認する,
    # 2: candidate値ごとに整数型と境界を確認する]
    # 引数: [spec: 整数設定, name: 設定名, minimum: 許容下限, maximum: 許容上限]
    # 戻り値: []
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
    # 責務: [_validate_numeric_candidates: 数値候補群の型・有限性・境界を検査する]
    # 処理: [1: bool・非数値・非有限値・範囲外値を拒否する]
    # 引数: [values: 検査する数値候補, name: 設定名, minimum: 許容下限, maximum: 許容上限]
    # 戻り値: []
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
    # 責務: [_candidate_values: 設定から空でないcandidate sequenceを取得する]
    # 処理: [1: valuesのsequence型と非空条件を確認する]
    # 引数: [spec: candidate設定mapping, name: 設定名]
    # 戻り値: [検証済みcandidate sequence]
    # }
    @staticmethod
    def _candidate_values(spec: Mapping[str, Any], name: str) -> Sequence[Any]:
        values = spec.get("values")
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ValueError(f"{name} candidates must be a non-empty list")
        return values

    # {
    # 責務: [_resolve_scalar: fixed・range・candidate modeから単一値を選ぶ]
    # 処理: [1: 設定mappingとmodeを読む, 2: 許可modeに応じて固定値・random値・候補を返す,
    # 3: その他のmodeを拒否する]
    # 引数: [spec: scalar設定mapping, name: 設定名, allow_range: rangeを許可するか,
    # allow_candidates: candidateを許可するか]
    # 戻り値: [選択した未型付けscalar値]
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
