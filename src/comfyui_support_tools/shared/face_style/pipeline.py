"""Fail-closed orchestration and exact non-target compositing for face style edits."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from PIL import Image, ImageChops

from .contracts import (
    BangsPolicy,
    FaceRegion,
    FaceSelection,
    FaceStyleBackend,
    FaceStyleCandidate,
    FaceStyleEvaluator,
    FaceStyleMetrics,
    FaceStyleRequest,
    FaceStyleResult,
)


# {
# 責務: [FaceStyleService: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceStyleService:
    """Runs pluggable face parsing, style backends and preservation evaluators.

    Identity and expression scores are never guessed. A candidate cannot be
    accepted until a host-provided evaluator measures the requested anchors.
    """

    # {
    # 責務: [__init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, backends]
    # 戻り値: [処理結果]
    # }
    def __init__(
        self,
        backends: Iterable[FaceStyleBackend] = (),
        *,
        region_provider: object | None = None,
        evaluator: FaceStyleEvaluator | None = None,
        max_candidates: int = 4,
        acceptance_threshold: float = 0.8,
    ) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if not 0 <= acceptance_threshold <= 1:
            raise ValueError("acceptance_threshold must be between 0 and 1")
        self.backends = tuple(backends)[:max_candidates]
        self.region_provider = region_provider
        self.evaluator = evaluator
        self.acceptance_threshold = acceptance_threshold

    # {
    # 責務: [run: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, request]
    # 戻り値: [処理結果]
    # }
    def run(self, request: FaceStyleRequest) -> FaceStyleResult:
        regions = request.regions
        if not regions and self.region_provider is not None:
            find_faces = getattr(self.region_provider, "find_faces", None)
            if callable(find_faces):
                regions = tuple(find_faces(request.image))
        chosen = self._choose_regions(request, regions)
        if not chosen:
            return FaceStyleResult(
                (), None, ("No face regions were supplied or detected; no edit was attempted.",)
            )
        if any(region.confidence < request.confidence_threshold for region in chosen):
            return FaceStyleResult(
                (), None, ("Face localization confidence is below the requested threshold.",)
            )
        mask = self._combined_mask(request, chosen)
        if mask.getbbox() is None:
            return FaceStyleResult((), None, ("The selected face edit mask is empty.",))
        if not self.backends:
            return FaceStyleResult(
                (),
                None,
                (
                    "No face-style editing backend is configured; install or inject a supported host backend.",
                ),
            )
        candidates: list[FaceStyleCandidate] = []
        for backend in self.backends:
            try:
                generated = backend.edit(
                    request.image.copy(), mask.copy(), request.target, request.prompt
                )
                if generated.size != request.image.size:
                    raise ValueError("backend changed image dimensions")
                generated = generated.convert(request.image.mode)
                composed = (
                    Image.composite(generated, request.image, mask)
                    if request.preserve_outside_mask
                    else generated
                )
                if self.evaluator is None:
                    metrics = FaceStyleMetrics()
                    warnings = (
                        "No face-style preservation evaluator is configured; candidate requires manual review.",
                    )
                else:
                    metrics = self.evaluator.evaluate(request.image, composed, mask, request.target)
                    warnings = ()
                accepted = (
                    metrics.safe_to_accept
                    and metrics.style_match is not None
                    and metrics.style_match >= self.acceptance_threshold
                    and min(
                        metrics.identity_preservation or 0,
                        metrics.expression_preservation or 0,
                        metrics.pose_preservation or 0,
                        metrics.gaze_preservation or 0,
                        metrics.non_target_preservation,
                    )
                    >= self.acceptance_threshold
                )
                candidates.append(
                    FaceStyleCandidate(
                        image=composed,
                        face_ids=tuple(region.face_id for region in chosen),
                        metrics=metrics,
                        warnings=warnings,
                        accepted=accepted,
                    )
                )
            except Exception as exc:  # Keep one failed backend from hiding other candidates.
                candidates.append(
                    FaceStyleCandidate(
                        image=request.image.copy(),
                        face_ids=tuple(region.face_id for region in chosen),
                        metrics=FaceStyleMetrics(),
                        warnings=(
                            f"Backend {getattr(backend, 'name', type(backend).__name__)} failed: {exc}",
                        ),
                    )
                )
        ranked = sorted(
            candidates,
            key=lambda item: (
                item.accepted,
                item.metrics.style_match or 0.0,
                item.metrics.identity_preservation or 0.0,
            ),
            reverse=True,
        )
        best = next((index for index, candidate in enumerate(ranked) if candidate.accepted), None)
        return FaceStyleResult(
            tuple(ranked),
            best,
            ()
            if best is not None
            else (
                "No candidate met the preservation acceptance threshold; review candidates manually.",
            ),
        )

    # {
    # 責務: [_choose_regions: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [request, regions]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _choose_regions(
        request: FaceStyleRequest, regions: tuple[FaceRegion, ...]
    ) -> tuple[FaceRegion, ...]:
        if request.selection is FaceSelection.MAIN:
            return (max(regions, key=lambda region: _area(region.face_mask)),) if regions else ()
        if request.selection is FaceSelection.SELECTED:
            wanted = set(request.selected_face_ids[:1])
            return tuple(region for region in regions if region.face_id in wanted)
        if request.selection is FaceSelection.GROUP:
            wanted = set(request.selected_face_ids)
            return tuple(region for region in regions if region.face_id in wanted)
        return tuple(regions)

    # {
    # 責務: [_combined_mask: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [request, regions]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _combined_mask(request: FaceStyleRequest, regions: tuple[FaceRegion, ...]) -> Image.Image:
        mask = Image.new("L", request.image.size, 0)
        for region in regions:
            face = region.face_mask.convert("L")
            if request.target.preserve_hair or request.target.bangs_policy in (
                BangsPolicy.PRESERVE,
                BangsPolicy.UNDER_HAIR,
            ):
                if region.hair_overlap_mask is not None:
                    face = ImageChops.subtract(face, region.hair_overlap_mask.convert("L"))
            mask = ImageChops.lighter(mask, face)
        return mask


# {
# 責務: [_area: face style retouchの処理または検証を行う]
# 処理: [1: 入力を検証する, 2: 結果を返す]
# 引数: [mask]
# 戻り値: [処理結果]
# }
def _area(mask: Image.Image) -> int:
    return sum(mask.convert("L").getdata())


# {
# 責務: [CallableFaceStyleBackend: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class CallableFaceStyleBackend:
    """Small adapter for a host-supplied inpaint or instruction-edit function."""

    # {
    # 責務: [__init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, name, edit]
    # 戻り値: [処理結果]
    # }
    def __init__(
        self, name: str, edit: Callable[[Image.Image, Image.Image, object, str], Image.Image]
    ) -> None:
        self.name = name
        self._edit = edit

    # {
    # 責務: [edit: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, image, mask, target, prompt]
    # 戻り値: [処理結果]
    # }
    def edit(
        self, image: Image.Image, mask: Image.Image, target: object, prompt: str
    ) -> Image.Image:
        return self._edit(image, mask, target, prompt)


# {
# 責務: [CallableFaceStyleEvaluator: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class CallableFaceStyleEvaluator:
    """Adapter preserving a host's identity/style evaluation implementation."""

    # {
    # 責務: [__init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, evaluate]
    # 戻り値: [処理結果]
    # }
    def __init__(
        self, evaluate: Callable[[Image.Image, Image.Image, Image.Image, object], FaceStyleMetrics]
    ) -> None:
        self._evaluate = evaluate

    # {
    # 責務: [evaluate: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, source, candidate, mask, target]
    # 戻り値: [処理結果]
    # }
    def evaluate(
        self, source: Image.Image, candidate: Image.Image, mask: Image.Image, target: object
    ) -> FaceStyleMetrics:
        measured = self._evaluate(source, candidate, mask, target)
        # Prevent a faulty plugin from claiming non-target preservation when
        # the final hard composite changed pixels outside the requested mask.
        outside = ImageChops.invert(mask.convert("L"))
        source_outside = Image.composite(source, Image.new(source.mode, source.size), outside)
        candidate_outside = Image.composite(
            candidate, Image.new(candidate.mode, candidate.size), outside
        )
        exact = source_outside.tobytes() == candidate_outside.tobytes()
        return replace(
            measured,
            non_target_preservation=1.0 if exact else min(measured.non_target_preservation, 0.0),
        )
