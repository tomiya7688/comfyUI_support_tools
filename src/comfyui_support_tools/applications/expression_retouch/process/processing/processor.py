"""Capability-routed local expression editing and candidate ranking."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from comfyui_support_tools.applications.expression_retouch.process.messenger.data_messenger import (
    ExpressionRetouchDataMessenger,
)
from comfyui_support_tools.applications.expression_retouch.process.processing.presets import (
    resolve_expression_target,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    ExpressionBackendCapabilities,
    ExpressionCandidate,
    ExpressionEditRequest,
    ExpressionEvaluation,
    ExpressionMode,
    ExpressionRetouchBackend,
    ExpressionRetouchResult,
    ExpressionSemanticEvaluator,
    FaceAnalysis,
)


# {
#   責務: [ExpressionRetouchProcessor: orchestrate local face editing and auditable candidate ranking]
#   フィールド: [detector, named backend registry, optional semantic evaluator, immutable artifact store]
#   処理: [analyze, select face/mask, capability-route, generate Top-N, measure preservation, composite locally, persist history]
# }
class ExpressionRetouchProcessor:
    # {
    #   責務: [__init__: configure face analysis, backend adapters and candidate evaluator]
    #   処理: [bind replaceable dependencies and initialize an empty backend registry]
    #   引数: [detector: injected face analyzer, store: injected artifact storage, evaluator: optional semantic evaluator]
    #   戻り値: []
    # }
    def __init__(
        self,
        data: ExpressionRetouchDataMessenger,
        evaluator: ExpressionSemanticEvaluator | None = None,
    ) -> None:
        self._data = data
        self._evaluator = evaluator
        self._backends: dict[str, ExpressionRetouchBackend] = {}

    # {
    #   責務: [register_backend: register one capability-described expression editor]
    #   処理: [validate stable backend ID and prevent accidental replacement]
    #   引数: [backend: expression backend implementation]
    #   戻り値: []
    # }
    def register_backend(self, backend: ExpressionRetouchBackend) -> None:
        name = backend.backend_id
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("backend ID must contain only letters, numbers, underscore, or hyphen")
        if name in self._backends:
            raise ValueError(f"expression backend is already registered: {name}")
        if not isinstance(backend.capabilities, ExpressionBackendCapabilities):
            raise TypeError("expression backend must expose validated capability metadata")
        self._backends[name] = backend

    # {
    #   責務: [available_backends: list configured backend identifiers]
    #   処理: [return deterministic registry order]
    #   引数: [self: processor]
    #   戻り値: [tuple[str, ...]: available names]
    # }
    @property
    def available_backends(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))

    # {
    #   責務: [analyze: expose face detections for preview and face selection]
    #   処理: [normalize EXIF orientation and run the configured detector]
    #   引数: [source_image: encoded source image]
    #   戻り値: [FaceAnalysis: ordered detections and detector limitations]
    # }
    def analyze(self, source_image: bytes) -> FaceAnalysis:
        return self._data.analyze(self._data.normalize(source_image))

    # {
    #   責務: [preview_mask: generate the detector's current automatic mask for UI preview]
    #   処理: [1: validate selected face index, 2: return mask from the Data messenger]
    #   引数: [analysis: current face analysis, face_index: target ordinal, parts: selected regions]
    #   戻り値: [bytes: automatic grayscale mask]
    # }
    def preview_mask(self, analysis: FaceAnalysis, face_index: int, parts: tuple) -> bytes:
        if not 0 <= face_index < len(analysis.faces):
            raise ValueError("selected face index is outside the detected faces")
        return self._data.mask(analysis.image_size, analysis.faces[face_index], parts, None)

    # {
    #   責務: [retouch: generate, evaluate, locally composite, rank, and persist candidates]
    #   処理: [1: canonicalize source and detect faces, 2: validate target and route capability, 3: create mask and candidate variants, 4: evaluate raw changes, 5: composite outside-mask source pixels, 6: save all metadata]
    #   引数: [request: expression intent and preservation settings, workspace: user-selected output folder, backend_id: optional preferred backend]
    #   戻り値: [ExpressionRetouchResult: ordered persisted candidates and selected index]
    # }
    def retouch(
        self,
        request: ExpressionEditRequest,
        workspace: str | Path,
        backend_id: str | None = None,
    ) -> ExpressionRetouchResult:
        request = replace(
            request,
            target=resolve_expression_target(request.natural_language, request.target),
        )
        normalized_source = self._data.normalize(request.source_image)
        normalized_request = replace(request, source_image=normalized_source)
        analysis = self._data.analyze(normalized_source)
        if not analysis.faces:
            raise ValueError("no frontal face was detected; select an image with a visible face")
        if request.face_index >= len(analysis.faces):
            raise ValueError("selected face index is outside the detected faces")
        face = analysis.faces[request.face_index]
        backend = self._resolve_backend(backend_id, request.mode, analysis.image_size)
        mask = self._data.mask(analysis.image_size, face, request.edit_regions, request.manual_mask)
        raw_candidates: list[tuple[bytes, ExpressionEvaluation, int | None]] = []
        for index in range(request.candidate_count):
            factor = self._candidate_factor(index, request.candidate_count)
            candidate_request = replace(
                normalized_request,
                intensity=min(1.0, request.intensity * factor),
                denoise=min(1.0, request.denoise * factor),
                seed=None if request.seed is None else request.seed + index,
                candidate_count=1,
            )
            seed = candidate_request.seed
            raw = backend.edit(candidate_request, mask, seed)
            identity_proxy, locality, limitations = self._data.measure(normalized_source, raw, mask)
            evaluation = (
                self._evaluator.evaluate(candidate_request, face, normalized_source, raw, mask)
                if self._evaluator is not None
                else ExpressionEvaluation(
                    expression_match=None,
                    identity_preservation=identity_proxy,
                    non_target_preservation=identity_proxy,
                    locality=locality,
                    limitations=limitations,
                )
            )
            if not isinstance(evaluation, ExpressionEvaluation):
                raise TypeError("semantic evaluator must return ExpressionEvaluation")
            composited = self._data.composite(normalized_source, raw, mask)
            raw_candidates.append((composited, evaluation, seed))
        order = sorted(
            range(len(raw_candidates)),
            key=lambda index: raw_candidates[index][1].ranking_score,
            reverse=True,
        )
        ordered = [raw_candidates[index] for index in order]
        candidate_rows = tuple(
            (
                image,
                {
                    "backend_id": backend.backend_id,
                    "seed": seed,
                    "evaluation": asdict(evaluation),
                    "ranking_score": evaluation.ranking_score,
                },
            )
            for image, evaluation, seed in ordered
        )
        metadata = {
            "target": request.target.value,
            "mode": request.mode.value,
            "intensity": request.intensity,
            "face_index": request.face_index,
            "face_bbox": face.bbox,
            "edit_regions": [part.value for part in request.edit_regions],
            "parameters": asdict(request.parameters),
            "natural_language": request.natural_language,
            "preserve_identity": request.preserve_identity,
            "preserve_background": request.preserve_background,
            "denoise": request.denoise,
            "backend_id": backend.backend_id,
            "capabilities": asdict(backend.capabilities),
            "warnings": list(analysis.warnings),
        }
        source_hash, paths, mask_path, manifest = self._data.save_run(
            workspace, normalized_source, mask, candidate_rows, metadata
        )
        candidates = tuple(
            ExpressionCandidate(path, mask_path, manifest, backend.backend_id, seed, evaluation)
            for path, (_image, evaluation, seed) in zip(paths, ordered, strict=True)
        )
        selected_candidate = 0
        warnings = analysis.warnings
        if self._evaluator is None:
            warnings += (
                "No semantic expression evaluator is configured; ranking uses identity/locality proxies only.",
            )
        return ExpressionRetouchResult(
            source_hash,
            request.target,
            analysis.faces,
            candidates,
            selected_candidate,
            warnings,
        )

    # {
    #   責務: [_resolve_backend: choose an editor that supports the requested face mode and local mask]
    #   処理: [1: use an explicitly selected ID if provided, 2: check appearance mode, mask support and max resolution]
    #   引数: [self: processor, backend_id: optional preferred ID, mode: requested appearance, image_size: source dimensions]
    #   戻り値: [ExpressionRetouchBackend: compatible local editing backend]
    # }
    def _resolve_backend(
        self,
        backend_id: str | None,
        mode: ExpressionMode,
        image_size: tuple[int, int],
    ) -> ExpressionRetouchBackend:
        if backend_id is not None:
            names = (backend_id,)
        else:
            names = self.available_backends
        for name in names:
            backend = self._backends.get(name)
            if backend is None:
                continue
            capabilities = backend.capabilities
            if (
                mode in capabilities.modes
                and capabilities.local_mask
                and max(image_size) <= capabilities.max_resolution
            ):
                return backend
        raise RuntimeError(
            "no configured expression backend supports this mode, resolution, and local-mask request"
        )

    # {
    #   責務: [_candidate_factor: vary candidate edit strength for conservative-to-strong alternatives]
    #   処理: [spread N attempts over a bounded 0.7..1.3 strength schedule]
    #   引数: [index: candidate order, count: number of candidate attempts]
    #   戻り値: [float: candidate strength multiplier]
    # }
    @staticmethod
    def _candidate_factor(index: int, count: int) -> float:
        if count == 1:
            return 1.0
        return 0.7 + 0.6 * index / (count - 1)
