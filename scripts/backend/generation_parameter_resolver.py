"""Resolve Random Image generation settings once for each image."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from src.comfyui_support_tools.shared.contracts.resolved_generation_parameters import (
    ResolvedGenerationParameters,
)


# {
# 責務: [ ParameterSpec: parameter入力UI/validation/backend binding用schemaを表す ]
# フィールド: [ name: key, value_type: strategy ID, minimum/maximum: numeric bounds, namespace: backend namespace, required: required flag ]
# 処理: []
# }
@dataclass(frozen=True)
class ParameterSpec:
    name: str
    value_type: str
    minimum: float | int | None = None
    maximum: float | int | None = None
    namespace: str | None = None
    required: bool = True
    default: Any = None
    choices: tuple[str, ...] = ()

    # {
    # 責務: [__post_init__: schema descriptorのidentityとboundsを検証する]
    # 処理: [1: field値を検査する 2: type別boundsとchoicesを確認する]
    # 引数: [self: parameter spec]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.name or any(character.isspace() for character in self.name):
            raise ValueError("parameter name must be non-empty and contain no whitespace")
        if not self.value_type or any(character.isspace() for character in self.value_type):
            raise ValueError("parameter value_type must be non-empty and contain no whitespace")
        if self.namespace is not None and (
            not self.namespace or any(character.isspace() for character in self.namespace)
        ):
            raise ValueError("parameter namespace must be non-empty and contain no whitespace")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("parameter numeric bounds must provide both minimum and maximum")
        if self.minimum is not None:
            bounds = (self.minimum, self.maximum)
            if any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in bounds
            ):
                raise ValueError("parameter bounds must be finite numbers")
            try:
                finite_bounds = all(math.isfinite(value) for value in bounds)
            except OverflowError:
                finite_bounds = False
            if not finite_bounds:
                raise ValueError("parameter bounds must be finite numbers")
            if self.minimum > self.maximum:
                raise ValueError("parameter minimum cannot exceed maximum")
            if self.value_type == "integer" and any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in (self.minimum, self.maximum)
            ):
                raise ValueError("integer parameter bounds must be integers")
        if self.value_type == "choice":
            if any(not isinstance(choice, str) or not choice.strip() for choice in self.choices):
                raise ValueError("choice parameter choices must be non-empty strings")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError("choice parameter choices must be unique")


# {
# 責務: [ ParameterSpecRegistry: specとvalue strategyを拡張可能に登録する ]
# フィールド: [ _specs: parameter schema, _strategies: strategy callback ]
# 処理: []
# }
class ParameterSpecRegistry:
    # {
    # 責務: [ __init__: registryを初期化する ]
    # 処理: [ 1: 空のschemaとstrategy mapを作る ]
    # 引数: [ self: registry instance ]
    # 戻り値: []
    # }
    def __init__(self) -> None:
        self._specs: dict[str, ParameterSpec] = {}
        self._strategies: dict[str, Any] = {}

    # {
    # 責務: [ register_strategy: strategy IDをresolver callbackへ結びつける ]
    # 処理: [ 1: 重複strategyを拒否する, 2: callbackを登録する ]
    # 引数: [ self: registry, value_type: strategy ID, strategy: resolver callback ]
    # 戻り値: []
    # }
    def register_strategy(self, value_type: str, strategy: Any) -> None:
        if not value_type or any(character.isspace() for character in value_type):
            raise ValueError("parameter strategy ID must be non-empty and contain no whitespace")
        if not callable(strategy):
            raise ValueError(f"Parameter strategy {value_type} must be callable")
        if value_type in self._strategies:
            raise ValueError(f"Duplicate parameter strategy: {value_type}")
        self._strategies[value_type] = strategy

    # {
    # 責務: [ register: parameter specを一意に登録する ]
    # 処理: [ 1: 重複keyと未知strategyを確認する, 2: specを保存する ]
    # 引数: [ self: registry, spec: parameter descriptor ]
    # 戻り値: []
    # }
    def register(self, spec: ParameterSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate generation parameter: {spec.name}")
        if spec.value_type not in self._strategies:
            raise ValueError(f"Unknown parameter strategy: {spec.value_type}")
        self._specs[spec.name] = spec

    # {
    # 責務: [ resolve: schemaに応じたstrategyでparameterを解決する ]
    # 処理: [ 1: namespace inputを選択する, 2: required/defaultを適用する, 3: strategyを実行する ]
    # 引数: [ self: registry, resolver: strategy host, configuration: input mapping ]
    # 戻り値: [ common: 共通parameter, backend: backendごとのparameter ]
    # }
    def resolve(self, resolver: "GenerationParameterResolver", configuration: Mapping[str, Any]):
        common: dict[str, Any] = {}
        backend: dict[str, dict[str, Any]] = {}
        for spec in self._specs.values():
            values = configuration
            if spec.namespace:
                namespace_values = configuration.get(spec.namespace, {})
                if not isinstance(namespace_values, Mapping):
                    raise ValueError(f"{spec.namespace} parameter namespace must be an object")
                values = namespace_values
            raw = values.get(spec.name, spec.default)
            if raw is None and spec.required:
                raise ValueError(f"{spec.name} configuration is required")
            if raw is None:
                continue
            value = self._strategies[spec.value_type](resolver, spec, raw)
            if spec.namespace:
                backend.setdefault(spec.namespace, {})[spec.name] = value
            else:
                common[spec.name] = value
        return common, backend

    # {
    # 責務: [ schema: UIとpresetが共有するparameter descriptorを返す ]
    # 処理: [ 1: 登録順にdescriptorを直列化可能なmappingへ変換する ]
    # 引数: [ self: registry instance ]
    # 戻り値: [ schema: UI/preset用descriptor列 ]
    # }
    def schema(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "name": spec.name,
                "type": spec.value_type,
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "namespace": spec.namespace,
                "required": spec.required,
                "default": spec.default,
                "choices": list(spec.choices),
            }
            for spec in self._specs.values()
        )


# {
# 責務: [ _number_strategy: NumericRangeSpecを解決する ]
# 処理: [ 1: boundsを必須化する, 2: number resolverを呼ぶ ]
# 引数: [ resolver: host, spec: schema, value: config ]
# 戻り値: [ number: resolved float ]
# }
def _number_strategy(resolver, spec: ParameterSpec, value: Any) -> float:
    if spec.minimum is None or spec.maximum is None:
        raise ValueError(f"{spec.name} numeric schema requires minimum and maximum")
    return resolver._resolve_number(value, spec.name, float(spec.minimum), float(spec.maximum))


# {
# 責務: [ _integer_strategy: IntegerRangeSpecを解決する ]
# 処理: [ 1: boundsを必須化する, 2: integer resolverを呼ぶ ]
# 引数: [ resolver: host, spec: schema, value: config ]
# 戻り値: [ integer: resolved int ]
# }
def _integer_strategy(resolver, spec: ParameterSpec, value: Any) -> int:
    if spec.minimum is None or spec.maximum is None:
        raise ValueError(f"{spec.name} integer schema requires minimum and maximum")
    return resolver._resolve_integer(value, spec.name, int(spec.minimum), int(spec.maximum))


# {
# 責務: [ _resolution_strategy: ResolutionCandidateSpecを解決する ]
# 処理: [ 1: range設定を禁止してresolution validatorを使う ]
# 引数: [ resolver: host, spec: schema, value: config ]
# 戻り値: [ resolution: width/height ]
# }
def _resolution_strategy(resolver, spec: ParameterSpec, value: Any) -> dict[str, int]:
    return resolver._resolve_resolution(value)


# {
# 責務: [ _choice_strategy: ChoiceSpecを解決しschema choicesを検証する ]
# 処理: [ 1: choice resolverを呼ぶ, 2: schema choicesを確認する ]
# 引数: [ resolver: host, spec: schema, value: config ]
# 戻り値: [ choice: resolved string ]
# }
def _choice_strategy(resolver, spec: ParameterSpec, value: Any) -> str:
    if isinstance(value, Mapping) and value.get("mode") == "candidate" and spec.choices:
        candidates = resolver._candidate_values(value, spec.name)
        if any(candidate not in spec.choices for candidate in candidates):
            raise ValueError(f"{spec.name} candidates must use configured choices")
    resolved = resolver._resolve_sampler(value)
    if spec.choices and resolved not in spec.choices:
        raise ValueError(f"{spec.name} must be one of the configured choices")
    return resolved


# {
# 責務: [ default_parameter_registry: 従来4項目の共通schemaと標準strategyを組み立てる ]
# 処理: [ 1: built-in strategyを登録する, 2: 互換parameter specを登録する ]
# 引数: []
# 戻り値: [ registry: 初期parameter registry ]
# }
def default_parameter_registry() -> ParameterSpecRegistry:
    registry = ParameterSpecRegistry()
    for name, strategy in (
        ("number", _number_strategy),
        ("integer", _integer_strategy),
        ("resolution", _resolution_strategy),
        ("choice", _choice_strategy),
    ):
        registry.register_strategy(name, strategy)
    for spec in (
        ParameterSpec("cfg", "number", 0.0, 50.0),
        ParameterSpec("steps", "integer", 1, 150),
        ParameterSpec("resolution", "resolution"),
        ParameterSpec("sampler", "choice"),
    ):
        registry.register(spec)
    return registry


DEFAULT_PARAMETER_REGISTRY = default_parameter_registry()


class GenerationParameterResolver:
    """Validate and resolve fixed, ranged, and candidate generation settings."""

    def __init__(
        self,
        random_source: Any | None = None,
        registry: ParameterSpecRegistry | None = None,
    ) -> None:
        self._random = random_source or random.SystemRandom()
        self._registry = registry or DEFAULT_PARAMETER_REGISTRY

    # {
    #   責務: [resolve: 設定候補を検証し, 1枚分の確定済み型付き生成値を作る]
    #   処理: [CFG, step数, 解像度, samplerを抽選または固定値で解決する]
    #   引数: [self: resolver, configuration: GUI非依存の候補設定]
    #   戻り値: [ResolvedGenerationParameters: バックエンドへ渡す確定値]
    # }
    def resolve(self, configuration: Mapping[str, Any]) -> ResolvedGenerationParameters:
        if not isinstance(configuration, Mapping):
            raise ValueError("generation parameter configuration must be an object")
        values, backend_values = self._registry.resolve(self, configuration)
        required = {"cfg", "steps", "resolution", "sampler"}
        missing = required - values.keys()
        if missing:
            raise ValueError(f"required generation parameters are missing: {sorted(missing)}")
        resolution = values["resolution"]
        extras = {name: value for name, value in values.items() if name not in required}
        return ResolvedGenerationParameters(
            values["cfg"],
            values["steps"],
            resolution["width"],
            resolution["height"],
            values["sampler"],
            extras,
            backend_values,
        )

    def _resolve_number(self, spec: Any, name: str, minimum: float, maximum: float) -> float:
        self._validate_numeric_options(spec, name, minimum, maximum)
        value = self._resolve_scalar(spec, name, allow_range=True, allow_candidates=True)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
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
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 64 <= value <= 4096
            or value % 8
        ):
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

    def _validate_numeric_options(
        self, spec: Any, name: str, minimum: float, maximum: float
    ) -> None:
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
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not minimum <= value <= maximum
                ):
                    raise ValueError(
                        f"{name} candidates must be integers between {minimum} and {maximum}"
                    )

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
                raise ValueError(
                    f"{name} values must be finite numbers between {minimum} and {maximum}"
                )

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
            if not all(
                isinstance(item, (int, float)) and math.isfinite(item) for item in (lower, upper)
            ):
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
