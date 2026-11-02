"""Orchestrate safe LoRA composition, evaluator-backed search and export."""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from .analysis import analyze_interference, check_composition_compatibility, factor_pairs
from .contracts import (
    CompatibilityReport,
    EvaluationCase,
    EvaluationScore,
    LayerInterference,
    LoRAAdapter,
    LoRAComposition,
    MergeMethod,
    ScaleCandidate,
)
from .io import load_adapter, new_composition, save_composition, save_merged_lora, write_json_atomic
from .merge import merge_adapters


# {
# 責務: [CompositionEvaluator: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class CompositionEvaluator(Protocol):
    """Bridge that renders or measures each candidate with a fixed case."""

    # {
    # 責務: [__call__: evaluate one exact prompt, seed, and scale configuration]
    # 処理: [render or inspect the composition and return normalized concept metrics]
    # 引数: [adapters: selected LoRAs, global_scales: candidate global weights, layer_scales: optional local weights, case: fixed validation case]
    # 戻り値: [EvaluationScore: fidelity, controllability, quality and leakage metrics]
    # }
    def __call__(
        self,
        adapters: Sequence[LoRAAdapter],
        global_scales: Mapping[str, float],
        layer_scales: Mapping[str, Mapping[str, float]],
        case: EvaluationCase,
    ) -> EvaluationScore: ...


# {
# 責務: [CompositionComparisonEvaluator: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class CompositionComparisonEvaluator(Protocol):
    """Bridge that compares runtime stacking with a concrete merge method."""

    # {
    # 責務: [__call__: score one runtime or static composition candidate]
    # 処理: [render a fixed case using runtime stacking or the selected merged method]
    # 引数: [adapters: source LoRAs, global_scales: candidate weights, layer_scales: module overrides, case: fixed prompt and seed, merge_method: None for runtime stack or static algorithm]
    # 戻り値: [EvaluationScore: normalized multi-concept metrics]
    # }
    def __call__(
        self,
        adapters: Sequence[LoRAAdapter],
        global_scales: Mapping[str, float],
        layer_scales: Mapping[str, Mapping[str, float]],
        case: EvaluationCase,
        merge_method: MergeMethod | None,
    ) -> EvaluationScore: ...


# {
# 責務: [LoRACompositionApplication: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class LoRACompositionApplication:
    """Coordinate independent analysis, merge, evaluation and persistence modules."""

    # {
    # 責務: [__init__: configure bounded scale search and preference history]
    # 処理: [prepare a local preference file and reject invalid search budgets]
    # 引数: [preference_path: optional prior history file, candidate_budget: maximum evaluator calls]
    # 戻り値: [None: application ready]
    # }
    def __init__(self, preference_path: str | Path | None = None, candidate_budget: int = 5000):
        if candidate_budget <= 0 or candidate_budget > 100_000:
            raise ValueError("candidate_budget must be in 1..100000")
        self.preference_path = Path(preference_path).expanduser() if preference_path else None
        self.candidate_budget = candidate_budget

    # {
    # 責務: [load: load selected safetensors adapters with declared roles]
    # 処理: [pair paths with optional role labels and delegate parsing to the isolated safetensors adapter]
    # 引数: [paths: input files, roles: optional names to functional roles]
    # 戻り値: [tuple[LoRAAdapter, ...]: loaded independent adapters]
    # }
    def load(
        self, paths: Sequence[str | Path], roles: Mapping[str, str] | None = None
    ) -> tuple[LoRAAdapter, ...]:
        from .contracts import LoRARole

        role_map = roles or {}
        return tuple(
            load_adapter(path, LoRARole(role_map.get(Path(path).stem, "concept"))) for path in paths
        )

    # {
    # 責務: [preflight: ensure model identity and target modules are safe to combine]
    # 処理: [return compatibility findings without guessing unknown base identity]
    # 引数: [adapters: selected LoRAs, base_model: requested base identifier]
    # 戻り値: [CompatibilityReport: blocking and advisory findings]
    # }
    def preflight(
        self, adapters: Sequence[LoRAAdapter], base_model: str, base_architecture: str
    ) -> CompatibilityReport:
        return check_composition_compatibility(adapters, base_model, base_architecture)

    # {
    # 責務: [analyze: calculate per-layer numerical interference signals]
    # 処理: [produce norm, cosine, subspace, sign-conflict and spectrum findings]
    # 引数: [adapters: selected source LoRAs]
    # 戻り値: [tuple[LayerInterference, ...]: visualization-ready findings]
    # }
    def analyze(self, adapters: Sequence[LoRAAdapter]) -> tuple[LayerInterference, ...]:
        return analyze_interference(adapters)

    # {
    # 責務: [search_scales: evaluate bounded global and per-layer scale candidates]
    # 処理: [score every fixed prompt/seed with balanced multi-concept objectives and history priors]
    # 引数: [adapters: source LoRAs, cases: fixed prompts/seeds, evaluator: rendering and metric bridge, scale_grid: candidate values, layer_scale_grid: optional per-layer values]
    # 戻り値: [tuple[ScaleCandidate, ...]: best-first scored scale candidates]
    # }
    def search_scales(
        self,
        adapters: Sequence[LoRAAdapter],
        cases: Sequence[EvaluationCase],
        evaluator: CompositionEvaluator,
        scale_grid: Sequence[float] = (0.5, 0.75, 1.0),
        layer_scale_grid: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
    ) -> tuple[ScaleCandidate, ...]:
        if not cases or any(not case.prompt.strip() for case in cases):
            raise ValueError("at least one nonempty fixed validation prompt is required")
        base_architecture = adapters[0].architecture if adapters else None
        report = check_composition_compatibility(adapters, "unknown", base_architecture)
        # Base family is unknown during search; identity is still enforced pairwise.
        blocking = [
            finding
            for finding in report.findings
            if finding.blocking and finding.code != "base_mismatch"
        ]
        if blocking:
            raise ValueError(
                "cannot search incompatible LoRAs: " + "; ".join(item.message for item in blocking)
            )
        candidates = self._scale_candidates(adapters, scale_grid, layer_scale_grid or {})
        calls = len(candidates) * len(cases)
        if calls > self.candidate_budget:
            raise ValueError(
                f"scale search requires {calls} evaluations; budget is {self.candidate_budget}"
            )
        scored = []
        for global_scales, layer_scales in candidates:
            scores = tuple(evaluator(adapters, global_scales, layer_scales, case) for case in cases)
            if any(not self._valid_score(score) for score in scores):
                raise ValueError("composition evaluator must return finite metrics in [0, 1]")
            aggregate = (
                min(score.aggregate for score in scores) * 0.4
                + sum(score.aggregate for score in scores) / len(scores) * 0.6
            )
            scored.append(ScaleCandidate(global_scales, layer_scales, scores, aggregate))
        return tuple(sorted(scored, key=lambda item: item.aggregate_score, reverse=True))

    # {
    # 責務: [search_compositions: compare runtime stacking and static merge candidates]
    # 処理: [evaluate fixed prompt/seed cases across weighted, top-K and Zip-style methods]
    # 引数: [adapters: compatible source LoRAs, cases: fixed validation set, evaluator: runtime/static comparison bridge, scale_grid: candidate scales, layer_scale_grid: optional per-adapter module grids, methods: selected static merge methods]
    # 戻り値: [tuple[ScaleCandidate, ...]: best-first candidate scores including runtime stack baseline]
    # }
    def search_compositions(
        self,
        adapters: Sequence[LoRAAdapter],
        cases: Sequence[EvaluationCase],
        evaluator: CompositionComparisonEvaluator,
        scale_grid: Sequence[float] = (0.5, 0.75, 1.0),
        layer_scale_grid: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
        methods: Sequence[MergeMethod] = (
            MergeMethod.WEIGHTED,
            MergeMethod.TOP_K,
            MergeMethod.K_LORA,
            MergeMethod.ZIP_STYLE,
            MergeMethod.ZIP_LORA,
        ),
    ) -> tuple[ScaleCandidate, ...]:
        if not cases or not methods:
            raise ValueError("comparison requires validation cases and at least one merge method")
        base_architecture = adapters[0].architecture if adapters else None
        if not check_composition_compatibility(adapters, "unknown", base_architecture).compatible:
            raise ValueError("cannot compare incompatible LoRAs")
        global_candidates = self._scale_candidates(adapters, scale_grid, layer_scale_grid or {})
        runtime_scales = {adapter.name: 1.0 for adapter in adapters}
        candidates = [(runtime_scales, {adapter.name: {} for adapter in adapters}, None)]
        candidates.extend(
            (scales, layers, method) for scales, layers in global_candidates for method in methods
        )
        calls = len(candidates) * len(cases)
        if calls > self.candidate_budget:
            raise ValueError(
                f"composition comparison requires {calls} evaluations; budget is {self.candidate_budget}"
            )
        scored = []
        for scales, layers, method in candidates:
            scores = tuple(evaluator(adapters, scales, layers, case, method) for case in cases)
            if any(not self._valid_score(score) for score in scores):
                raise ValueError("composition evaluator must return finite metrics in [0, 1]")
            aggregate = (
                min(score.aggregate for score in scores) * 0.4
                + sum(score.aggregate for score in scores) / len(scores) * 0.6
            )
            scored.append(ScaleCandidate(scales, layers, scores, aggregate, method))
        return tuple(sorted(scored, key=lambda item: item.aggregate_score, reverse=True))

    # {
    # 責務: [_scale_candidates: construct a bounded search space with prior scales]
    # 処理: [enumerate global choices and optional per-layer overrides deterministically]
    # 引数: [adapters: source LoRAs, scale_grid: candidate values, layer_grid: per-layer values]
    # 戻り値: [tuple[tuple[dict, dict], ...]: candidate settings]
    # }
    def _scale_candidates(
        self,
        adapters: Sequence[LoRAAdapter],
        scale_grid: Sequence[float],
        layer_grid: Mapping[str, Mapping[str, Sequence[float]]],
    ) -> tuple[tuple[dict[str, float], dict[str, dict[str, float]]], ...]:
        values = tuple(dict.fromkeys(float(value) for value in scale_grid))
        if not values or any(not np.isfinite(value) or abs(value) > 4 for value in values):
            raise ValueError("scale_grid values must be finite and within [-4, 4]")
        priors = self.preference_priors()
        choices = []
        for adapter in adapters:
            options = list(values)
            if adapter.role.value == "slider":
                bounds = (adapter.slider_minimum, adapter.slider_maximum, adapter.slider_neutral)
                if (
                    any(not np.isfinite(value) for value in bounds)
                    or adapter.slider_minimum > adapter.slider_maximum
                ):
                    raise ValueError(f"{adapter.name} has invalid slider metadata")
                options = [
                    value
                    for value in options
                    if adapter.slider_minimum <= value <= adapter.slider_maximum
                ]
                if adapter.slider_minimum <= adapter.slider_neutral <= adapter.slider_maximum:
                    options.append(adapter.slider_neutral)
            if adapter.name in priors:
                prior = priors[adapter.name]
                if (
                    adapter.role.value != "slider"
                    or adapter.slider_minimum <= prior <= adapter.slider_maximum
                ):
                    options.append(prior)
            if not options:
                raise ValueError(f"scale grid does not overlap the valid range for {adapter.name}")
            choices.append(tuple(dict.fromkeys(options)))
        global_combinations = list(itertools.product(*choices))
        if len(global_combinations) > self.candidate_budget:
            raise ValueError("global scale grid exceeds the configured candidate budget")
        layers = (
            tuple(sorted(set.union(*(_adapter_layers(adapter) for adapter in adapters))))
            if adapters
            else ()
        )
        layer_options = []
        for layer in layers:
            for adapter in adapters:
                options = tuple(
                    float(value) for value in layer_grid.get(layer, {}).get(adapter.name, ())
                )
                if any(not np.isfinite(value) or abs(value) > 4 for value in options):
                    raise ValueError(
                        f"layer scale values for {adapter.name}/{layer} must be finite and within [-4, 4]"
                    )
                if options:
                    layer_options.append((adapter.name, layer, options))
        override_combinations = (
            list(itertools.product(*(options for _, _, options in layer_options)))
            if layer_options
            else [()]
        )
        total = len(global_combinations) * len(override_combinations)
        if total > self.candidate_budget:
            raise ValueError(
                "global and per-layer scale grid exceeds the configured candidate budget"
            )
        result = []
        for globals_tuple in global_combinations:
            global_map = {
                adapter.name: value for adapter, value in zip(adapters, globals_tuple, strict=True)
            }
            for overrides in override_combinations:
                layer_map = {
                    adapter.name: {
                        layer: value
                        for (name, layer, _), value in zip(layer_options, overrides, strict=True)
                        if name == adapter.name
                    }
                    for adapter in adapters
                }
                result.append((global_map, layer_map))
        return tuple(result)

    # {
    # 責務: [_valid_score: validate the evaluator's normalized metric contract]
    # 処理: [check all public metrics for finite [0, 1] values]
    # 引数: [score: evaluator result]
    # 戻り値: [bool: true when all metrics are normalized]
    # }
    @staticmethod
    def _valid_score(score: EvaluationScore) -> bool:
        values = tuple(vars(score).values())
        return all(np.isfinite(value) and 0 <= value <= 1 for value in values)

    # {
    # 責務: [export: create merged tensors and a portable runtime recipe]
    # 処理: [preflight, merge, write immutable artifacts and preserve source hashes and evaluation cases]
    # 引数: [adapters: source LoRAs, base_model: target model, base_architecture: declared architecture, method: composition algorithm, global_scales: selected values, destination: recipe output, layer_scales: optional overrides, cases: fixed validation prompts, score: optional candidate score, rank_limit: static output rank cap]
    # 戻り値: [LoRAComposition: generated recipe metadata]
    # }
    def export(
        self,
        adapters: Sequence[LoRAAdapter],
        base_model: str,
        base_architecture: str,
        method: MergeMethod,
        global_scales: Mapping[str, float],
        destination: str | Path,
        layer_scales: Mapping[str, Mapping[str, float]] | None = None,
        cases: Sequence[EvaluationCase] = (),
        score: float | None = None,
        rank_limit: int = 64,
    ) -> LoRAComposition:
        report = check_composition_compatibility(adapters, base_model, base_architecture)
        if not report.compatible:
            raise ValueError("LoRA compatibility preflight failed")
        output = Path(destination).expanduser()
        if output.suffix.casefold() != ".json":
            raise ValueError("runtime recipe destination must use a .json extension")
        static_path = output.with_suffix(".safetensors")
        tensors = merge_adapters(
            adapters,
            base_model,
            base_architecture,
            global_scales,
            method,
            layer_scales,
            rank_limit,
        )
        provenance = {
            "source_loras": json.dumps(
                [adapter.provenance for adapter in adapters], sort_keys=True
            ),
            "base_model": base_model,
            "base_model_family": adapters[0].family,
            "architecture": adapters[0].architecture,
            "ss_network_dim": str(rank_limit),
            "ss_network_alpha": str(rank_limit),
            "merge_method": method.value,
            "global_scales": json.dumps(dict(global_scales), sort_keys=True),
            "layer_scales": json.dumps(layer_scales or {}, sort_keys=True),
            "composition_schema": "1",
        }
        saved_static = save_merged_lora(tensors, static_path, provenance)
        composition = new_composition(
            tuple(adapters),
            base_model,
            method,
            dict(global_scales),
            {name: dict(values) for name, values in (layer_scales or {}).items()},
            score,
            tuple(cases),
            saved_static,
        )
        try:
            save_composition(composition, output)
        except Exception:
            saved_static.unlink(missing_ok=True)
            raise
        return composition

    # {
    # 責務: [record_preference: persist a user's reviewed scale choice]
    # 処理: [append a bounded pair of names, roles and chosen scales to atomic local history]
    # 引数: [adapters: selected source assets, scales: preferred global scales]
    # 戻り値: [None: preference available as future search prior]
    # }
    def record_preference(
        self, adapters: Sequence[LoRAAdapter], scales: Mapping[str, float]
    ) -> None:
        if self.preference_path is None:
            raise ValueError("preference_path must be configured to record user choices")
        if set(scales) != {adapter.name for adapter in adapters}:
            raise ValueError("preference scales must contain exactly the selected LoRA names")
        if any(not np.isfinite(value) or abs(value) > 4 for value in scales.values()):
            raise ValueError("preference scales must be finite and within [-4, 4]")
        history = self._read_preferences()
        history.append(
            {
                "scales": {name: float(value) for name, value in scales.items()},
                "roles": {adapter.name: adapter.role.value for adapter in adapters},
            }
        )
        write_json_atomic(self.preference_path, history[-1000:])

    # {
    # 責務: [preference_priors: calculate scale priors from prior user choices]
    # 処理: [average each known adapter scale from the last 1000 bounded preference records]
    # 引数: [None: use configured history path]
    # 戻り値: [dict[str, float]: previous mean scales]
    # }
    def preference_priors(self) -> dict[str, float]:
        values: dict[str, list[float]] = {}
        for record in self._read_preferences():
            for name, scale in record.get("scales", {}).items():
                if isinstance(name, str) and isinstance(scale, (float, int)) and np.isfinite(scale):
                    values.setdefault(name, []).append(float(scale))
        return {name: sum(scales) / len(scales) for name, scales in values.items() if scales}

    # {
    # 責務: [_read_preferences: load bounded preference history defensively]
    # 処理: [reject symlink, malformed, oversized, or unexpected preference documents]
    # 引数: [None: use configured history path]
    # 戻り値: [list[dict]: validated bounded history]
    # }
    def _read_preferences(self) -> list[dict]:
        if self.preference_path is None or not self.preference_path.exists():
            return []
        if (
            self.preference_path.is_symlink()
            or self.preference_path.stat().st_size > 4 * 1024 * 1024
        ):
            raise ValueError("preference history must be a bounded regular file")
        try:
            value = json.loads(self.preference_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("preference history is malformed") from error
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("preference history must contain a list of records")
        return value[-1000:]


# {
# 責務: [_adapter_layers: retrieve supported target layer names from factors]
# 処理: [normalize factor-pair keys by relying on the analyzer's validated parser]
# 引数: [adapter: loaded LoRA]
# 戻り値: [set[str]: target module names]
# }
def _adapter_layers(adapter: LoRAAdapter) -> set[str]:
    return set(factor_pairs(adapter))
