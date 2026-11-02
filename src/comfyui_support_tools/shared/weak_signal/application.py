"""Mode routing, backend registration, candidate ranking and evidence export."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Protocol

from .backend import PillowWeakSignalBackend, classify_weak_signal_mode
from .contracts import (
    ObservationInput,
    WeakSignalCandidate,
    WeakSignalMode,
    WeakSignalRequest,
    WeakSignalResult,
)


# {
#   責務: [WeakSignalBackend: selected mode用candidate generator interfaceを定義する]
#   フィールド: [supported_modes, generate]
#   処理: [plugins implement only their modes and return common provenance-aware candidates]
# }
class WeakSignalBackend(Protocol):
    # {
    #   責務: [supported_modes: backendが対応するmodeを公開する]
    #   処理: [expose explicit task support for registry validation]
    #   引数: [self: processing adapter]
    #   戻り値: [frozenset[WeakSignalMode]: supported resolved modes]
    # }
    @property
    def supported_modes(self) -> frozenset[WeakSignalMode]: ...

    # {
    #   責務: [generate: one observationからrank可能なcandidateを作成する]
    #   処理: [produce encoded candidate frames with provenance, confidence and named score dimensions]
    #   引数: [observation: original frames, request: preferences, mode: selected prior]
    #   戻り値: [tuple[WeakSignalCandidate, ...]: alternative outputs]
    # }
    def generate(
        self, observation: ObservationInput, request: WeakSignalRequest, mode: WeakSignalMode
    ) -> tuple[WeakSignalCandidate, ...]: ...


# {
#   責務: [WeakSignalBackendRegistry: modeごとのbuilt-in/research adapterを管理する]
#   フィールド: [WeakSignalMode -> ordered backend list]
#   処理: [Touka, Pillow, reflection research backends register without UI/core changes]
# }
class WeakSignalBackendRegistry:
    # {
    #   責務: [__init__: optional adaptersをmode別registryへ登録する]
    #   処理: [start empty and install conservative Pillow priors unless overridden]
    #   引数: [backends: optional mode/backend mapping]
    #   戻り値: []
    # }
    def __init__(self, backends: tuple[WeakSignalBackend, ...] = ()) -> None:
        self._backends: dict[WeakSignalMode, list[WeakSignalBackend]] = {}
        for backend in backends:
            for mode in backend.supported_modes:
                self.register(mode, backend)
        default_backend = PillowWeakSignalBackend()
        for mode in default_backend.supported_modes:
            if mode not in self._backends:
                self.register(mode, default_backend)

    # {
    #   責務: [register: one backendをselected modeへ追加する]
    #   処理: [reject AUTO and require backend-declared support before registration]
    #   引数: [mode: concrete task mode, backend: candidate generator]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: unsupported backend/mode registration]
    # }
    def register(self, mode: WeakSignalMode, backend: WeakSignalBackend) -> None:
        if not isinstance(mode, WeakSignalMode) or mode is WeakSignalMode.AUTO:
            raise ValueError("only resolved weak-signal modes can be registered")
        if mode not in backend.supported_modes:
            raise ValueError(f"backend does not declare support for {mode.value}")
        self._backends.setdefault(mode, []).append(backend)

    # {
    #   責務: [get: selected modeのgeneratorを優先順位順で取得する]
    #   処理: [select first registered backend without silent cross-mode fallback]
    #   引数: [mode: resolved task mode]
    #   戻り値: [WeakSignalBackend: registered compatible processor]
    #   エラー: [LookupError: no backend for requested mode]
    # }
    def get(self, mode: WeakSignalMode) -> WeakSignalBackend:
        backends = self._backends.get(mode, [])
        if not backends:
            raise LookupError(f"no weak-signal backend is registered for {mode.value}")
        return backends[0]

    # {
    #   責務: [modes: executable modesをstable orderで一覧化する]
    #   処理: [exclude AUTO and return modes with at least one registered processor]
    #   引数: [self: backend registry]
    #   戻り値: [tuple[WeakSignalMode, ...]: selectable modes]
    # }
    @property
    def modes(self) -> tuple[WeakSignalMode, ...]:
        return tuple(sorted(self._backends, key=lambda mode: mode.value))


# {
#   責務: [WeakSignalApplication: common observation to candidate processingを統括する]
#   フィールド: [backend registry]
#   処理: [manual/auto mode, named score ranking, provenance-preserving outputsを扱う]
# }
class WeakSignalApplication:
    # {
    #   責務: [__init__: backend registryをapplicationへ注入する]
    #   処理: [retain an extensible mode-specific backend registry]
    #   引数: [registry: registered classical/Touka/research processors]
    #   戻り値: []
    # }
    def __init__(self, registry: WeakSignalBackendRegistry | None = None) -> None:
        self._registry = registry or WeakSignalBackendRegistry()

    # {
    #   責務: [process: observation and modeからrank付きcandidate結果を作る]
    #   処理: [classify AUTO heuristically, invoke matching backend, and sort by conservative mode utility]
    #   引数: [observation: original input frames, request: mode/strength/count/alignment]
    #   戻り値: [WeakSignalResult: selected mode, alternatives and classifier provenance]
    #   エラー: [LookupError or ValueError: unsupported mode/backend or invalid observation]
    # }
    def process(
        self, observation: ObservationInput, request: WeakSignalRequest
    ) -> WeakSignalResult:
        if request.mode is WeakSignalMode.AUTO:
            mode, confidence, reason = classify_weak_signal_mode(observation)
        else:
            mode, confidence, reason = request.mode, 1.0, "user selected the mode manually"
        backend = self._registry.get(mode)
        candidates = backend.generate(observation, request, mode)
        ranked = tuple(sorted(candidates, key=lambda item: _candidate_rank(mode, item)))
        if not ranked:
            raise ValueError(f"backend returned no candidates for mode {mode.value}")
        if len(ranked) > request.candidate_count:
            ranked = ranked[: request.candidate_count]
        return WeakSignalResult(observation.observation_id, mode, ranked, confidence, reason)

    # {
    #   責務: [export: candidate frame imagesとprovenance JSON manifestを保存する]
    #   処理: [write each candidate/component to stable paths and atomically commit one evidence manifest]
    #   引数: [result: processed candidate set, output_dir: artifact directory]
    #   戻り値: [tuple[Path, ...]: candidate and manifest paths]
    #   エラー: [OSError: artifact output failure]
    # }
    def export(self, result: WeakSignalResult, output_dir: Path) -> tuple[Path, ...]:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        artifacts: list[Path] = []
        candidate_rows = []
        for candidate in result.candidates:
            safe_id = _safe_name(candidate.candidate_id)
            frame_paths = []
            for index, payload in enumerate(candidate.frames):
                path = destination / f"{safe_id}_frame_{index:04d}.png"
                _atomic_write(path, payload)
                artifacts.append(path)
                frame_paths.append(path.name)
            component_rows = []
            for component_name, component_frames in candidate.components:
                component_paths = []
                for index, payload in enumerate(component_frames):
                    path = destination / f"{safe_id}_{_safe_name(component_name)}_{index:04d}.png"
                    _atomic_write(path, payload)
                    artifacts.append(path)
                    component_paths.append(path.name)
                component_rows.append({"name": component_name, "frames": component_paths})
            candidate_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "mode": candidate.mode.value,
                    "generator": candidate.generator,
                    "strength": candidate.strength,
                    "confidence": candidate.confidence,
                    "scores": dict(candidate.scores),
                    "frames": frame_paths,
                    "components": component_rows,
                    "provenance": [
                        {
                            "region": item.region,
                            "kind": item.kind.value,
                            "confidence": item.confidence,
                            "generator": item.generator,
                            "note": item.note,
                        }
                        for item in candidate.provenance
                    ],
                }
            )
        manifest = {
            "schema": "weak-signal-evidence.v1",
            "observation_id": result.observation_id,
            "selected_mode": result.selected_mode.value,
            "mode_confidence": result.mode_confidence,
            "mode_reason": result.mode_reason,
            "candidates": candidate_rows,
            "ocr_input_candidates": [row["frames"][0] for row in candidate_rows if row["frames"]],
            "inspector_provenance": "See candidate.provenance and candidate.components for observed, enhanced, inferred, and completed data.",
        }
        manifest_path = destination / f"{_safe_name(result.observation_id)}.weak-signal.json"
        payload = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        _atomic_write(manifest_path, payload)
        return (*artifacts, manifest_path)


# {
#   責務: [_candidate_rank: task mode用のexplicit named-dimension utilityを作る]
#   処理: [prefer structure preservation and mode-specific measured proxies with stable tie breaking]
#   引数: [mode: selected mode, candidate: measured candidate]
#   戻り値: [tuple[float, str]: stable candidate order key]
# }
def _candidate_rank(mode: WeakSignalMode, candidate: WeakSignalCandidate) -> tuple[float, str]:
    scores = dict(candidate.scores)
    structure = scores.get("structure_retention", 0.0)
    contrast = scores.get("local_contrast_proxy", 0.0)
    weight = 0.35 if mode in {WeakSignalMode.WEAK_DETAIL, WeakSignalMode.PAPER_SHOWTHROUGH} else 0.2
    return -((1 - weight) * structure + weight * contrast), candidate.candidate_id


# {
#   責務: [_safe_name: user-derived artifact identifiersをfilesystem-safe文字列へ変換する]
#   処理: [retain ascii alphanumeric/dash/underscore and bound filename component length]
#   引数: [value: observation/candidate/component identifier]
#   戻り値: [str: safe non-empty filename stem]
# }
def _safe_name(value: str) -> str:
    name = "".join(
        character if character.isalnum() or character in "-_" else "_" for character in value
    )
    return name[:96].strip("._-") or "weak-signal"


# {
#   責務: [_atomic_write: artifact bytesを一時file経由でcommitする]
#   処理: [write payload completely then atomically replace destination]
#   引数: [destination: output path, payload: encoded image or JSON bytes]
#   戻り値: []
#   エラー: [OSError: write or replace failure]
# }
def _atomic_write(destination: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
    try:
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
