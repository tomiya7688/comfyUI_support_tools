"""Capture-set assessment, exposure fusion, and extensible Touka routing."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageChops, ImageStat

from comfyui_support_tools.shared.weak_signal import (
    EvidenceKind,
    ObservationInput,
    WeakSignalApplication,
    WeakSignalMode,
    WeakSignalRequest,
    WeakSignalResult,
)

from .contracts import CaptureQuality, CaptureSet
from .decode import RawFrameDecoder, decode_frame
from .quality import score_capture_set


# {
#   責務: [ExposureFusion: fused observationとsource provenanceを保持する]
#   フィールド: [png_bytes, source_paths, generator, caveat]
# }
@dataclass(frozen=True, slots=True)
class ExposureFusion:
    png_bytes: bytes
    source_paths: tuple[str, ...]
    generator: str = "exposure_normalized_mean_v1"
    caveat: str = (
        "Approximate sRGB fusion; registration and calibrated linear sensor data are not verified."
    )


# {
#   責務: [CaptureSetBackend: polarization/RAW等のspecialized Touka backend interfaceを定義する]
#   フィールド: [name, supports, process]
#   処理: [specialized backend receives original CaptureSet metadata and optional fusion pixels]
# }
class CaptureSetBackend(Protocol):
    # {
    #   責務: [name: backend routing provenanceを返す]
    #   処理: [expose stable adapter name]
    #   引数: [self: specialized capture backend]
    #   戻り値: [str: backend identifier]
    # }
    @property
    def name(self) -> str: ...

    # {
    #   責務: [supports: CaptureSetに対して専用処理可能か判定する]
    #   処理: [inspect explicit metadata/capabilities only]
    #   引数: [capture_set: imported observations]
    #   戻り値: [bool: backend can process the capture set]
    # }
    def supports(self, capture_set: CaptureSet) -> bool: ...

    # {
    #   責務: [process: specialized processorで候補を生成する]
    #   処理: [retain frame-level capture metadata and source bytes]
    #   引数: [capture_set: original observations, request: requested downstream task, fusion: optional exposure fusion]
    #   戻り値: [WeakSignalResult: evidence-aware candidate result]
    # }
    def process(
        self,
        capture_set: CaptureSet,
        request: WeakSignalRequest,
        fusion: ExposureFusion | None,
    ) -> WeakSignalResult: ...


# {
#   責務: [CaptureAssistantResult: capture quality, optional fusion, and downstream candidateを返す]
#   フィールド: [capture_set, quality, exposure_fusion, processing_result, route]
# }
@dataclass(frozen=True, slots=True)
class CaptureAssistantResult:
    capture_set: CaptureSet
    quality: tuple[CaptureQuality, ...]
    exposure_fusion: ExposureFusion | None
    processing_result: WeakSignalResult
    route: str
    interframe_difference_proxy: float | None = None
    guidance: tuple[str, ...] = ()


# {
#   責務: [CaptureAssistantApplication: local capture import dataをassessしcompatible backendへrouteする]
#   フィールド: [weak-signal fallback, optional RAW decoder, specialized backends]
#   処理: [score frames, fuse exposure brackets, prefer matching polarization backend, and retain single-image fallback]
# }
class CaptureAssistantApplication:
    # {
    #   責務: [__init__: processing adaptersをapplicationへ注入する]
    #   処理: [retain a portable local-only fallback and optional hardware-specific plugins]
    #   引数: [weak_signal: generic image processor, raw_decoder: optional RAW decoder, backends: specialized capture processors]
    #   戻り値: []
    # }
    def __init__(
        self,
        weak_signal: WeakSignalApplication | None = None,
        raw_decoder: RawFrameDecoder | None = None,
        backends: tuple[CaptureSetBackend, ...] = (),
    ) -> None:
        self._weak_signal = weak_signal or WeakSignalApplication()
        self._raw_decoder = raw_decoder
        self._backends = backends

    # {
    #   責務: [process: CaptureSet qualityとdownstream candidate resultを作る]
    #   処理: [evaluate every frame, create bracket fusion when possible, use polarization adapter or generic fallback]
    #   引数: [capture_set: imported local observations, request: requested weak-signal task]
    #   戻り値: [CaptureAssistantResult: quality, fusion, candidate and backend route]
    #   エラー: [RuntimeError or ValueError: required RAW decoder, unsafe image, or invalid alignment]
    # }
    def process(
        self, capture_set: CaptureSet, request: WeakSignalRequest
    ) -> CaptureAssistantResult:
        decoded = tuple(decode_frame(frame, self._raw_decoder) for frame in capture_set.frames)
        quality = score_capture_set(capture_set.frames, decoded)
        fusion = _fuse_exposure_bracket(capture_set, decoded)
        interframe_difference = _interframe_difference(decoded)
        guidance = (
            ("low_interframe_difference_check_capture_diversity",)
            if interframe_difference is not None and interframe_difference < 0.02
            else ()
        )
        polarization_backend = next(
            (
                backend
                for backend in self._backends
                if capture_set.has_polarization and backend.supports(capture_set)
            ),
            None,
        )
        if polarization_backend is not None:
            result = polarization_backend.process(capture_set, request, fusion)
            return CaptureAssistantResult(
                capture_set,
                quality,
                fusion,
                result,
                polarization_backend.name,
                interframe_difference,
                guidance,
            )
        observation = _build_observation(capture_set, decoded, fusion)
        effective_request = request
        if (
            fusion is None
            and capture_set.is_burst
            and not capture_set.aligned_frames_assumed
            and request.mode is WeakSignalMode.AUTO
        ):
            best_index = max(range(len(quality)), key=lambda index: quality[index].score)
            observation = ObservationInput(
                capture_set.capture_set_id,
                (_encode_png(decoded[best_index]),),
                metadata=(("selected_frame", capture_set.frames[best_index].relative_path),),
                input_provenance_note=(
                    "Best-scoring original frame selected from an unaligned burst; "
                    "cross-frame layer separation was skipped."
                ),
            )
            effective_request = WeakSignalRequest(
                mode=WeakSignalMode.WEAK_DETAIL,
                strength=request.strength,
                candidate_count=request.candidate_count,
            )
        result = self._weak_signal.process(observation, effective_request)
        fallback = (
            "weak_signal_burst"
            if capture_set.is_burst
            else "weak_signal_multiframe"
            if len(capture_set.frames) > 1
            else "single_image_fallback"
        )
        if effective_request is not request:
            fallback = "single_image_fallback:unaligned_burst"
        if capture_set.has_polarization:
            fallback += ":polarization_backend_unavailable"
        return CaptureAssistantResult(
            capture_set, quality, fusion, result, fallback, interframe_difference, guidance
        )

    # {
    #   責務: [write_manifest: local session diagnosticsをversioned JSONへ保存する]
    #   処理: [write capture metadata, hashes, quality measures, fusion provenance and actual routing choice]
    #   引数: [result: assessed session, destination: local sidecar path]
    #   戻り値: [bytes: manifest payload for caller-controlled local storage]
    # }
    def manifest(self, result: CaptureAssistantResult) -> bytes:
        value = {
            "schema": "capture-assistant-result.v1",
            "capture_set_id": result.capture_set.capture_set_id,
            "source": result.capture_set.source,
            "privacy": "local_only",
            "route": result.route,
            "interframe_difference_proxy": result.interframe_difference_proxy,
            "guidance": result.guidance,
            "aligned_frames_assumed": result.capture_set.aligned_frames_assumed,
            "frames": [
                {
                    "path": frame.relative_path,
                    "media_type": frame.media_type,
                    "format": frame.source_format,
                    "sha256": frame.sha256,
                    "capture_time": frame.capture_time,
                    "exposure_ev": frame.exposure_ev,
                    "iso": frame.iso,
                    "aperture": frame.aperture,
                    "polarization_angle": frame.polarization_angle,
                    "quality": {
                        "score": quality.score,
                        "blur_proxy": quality.blur_proxy,
                        "clipped_fraction": quality.clipped_fraction,
                        "warnings": quality.warnings,
                    },
                }
                for frame, quality in zip(result.capture_set.frames, result.quality, strict=True)
            ],
            "exposure_fusion": (
                {
                    "generator": result.exposure_fusion.generator,
                    "source_paths": result.exposure_fusion.source_paths,
                    "caveat": result.exposure_fusion.caveat,
                }
                if result.exposure_fusion
                else None
            ),
        }
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


# {
#   責務: [_build_observation: CaptureFrame sequenceをweak-signal contractへ変換する]
#   処理: [prefer bracket fusion as explicitly inferred evidence while preserving the original CaptureSet separately]
#   引数: [capture_set: original metadata, decoded: RGB observations, fusion: optional bracket combination]
#   戻り値: [ObservationInput: generic or specialized downstream input]
# }
def _build_observation(
    capture_set: CaptureSet, decoded, fusion: ExposureFusion | None
) -> ObservationInput:
    if fusion is not None:
        return ObservationInput(
            capture_set.capture_set_id,
            (fusion.png_bytes,),
            metadata=(
                ("capture_set_id", capture_set.capture_set_id),
                ("source_paths", ",".join(fusion.source_paths)),
            ),
            input_evidence_kind=EvidenceKind.INFERRED,
            input_generator=fusion.generator,
            input_provenance_note=fusion.caveat,
        )
    payloads = tuple(_encode_png(image) for image in decoded)
    media_kind = "image" if len(payloads) == 1 else "burst"
    metadata = tuple(
        (
            f"frame_{index:04d}",
            json.dumps(
                {
                    "path": frame.relative_path,
                    "media_type": frame.media_type,
                    "source_format": frame.source_format,
                    "sha256": frame.sha256,
                    "capture_time": frame.capture_time,
                    "exposure_ev": frame.exposure_ev,
                    "iso": frame.iso,
                    "aperture": frame.aperture,
                    "polarization_angle": frame.polarization_angle,
                },
                sort_keys=True,
            ),
        )
        for index, frame in enumerate(capture_set.frames)
    )
    return ObservationInput(
        capture_set.capture_set_id,
        payloads,
        media_kind,
        metadata,
        input_provenance_note="Capture Assistant imported and oriented image pixels; source RAW/image bytes and hashes remain in CaptureSet.",
    )


# {
#   責務: [_fuse_exposure_bracket: multiple exposure observationsを相対EVで近似統合する]
#   処理: [normalize to median EV and average same-sized RGB frames with explicit approximation caveat]
#   引数: [capture_set: exposure metadata and provenance, images: decoded RGB pixels]
#   戻り値: [ExposureFusion | None: fused PNG candidate or no bracket]
# }
def _fuse_exposure_bracket(capture_set: CaptureSet, images) -> ExposureFusion | None:
    if not capture_set.has_exposure_bracket:
        return None
    selected = [
        (frame, image)
        for frame, image in zip(capture_set.frames, images, strict=True)
        if frame.exposure_ev is not None
    ]
    if len({image.size for _frame, image in selected}) != 1:
        return None
    reference_ev = sorted(frame.exposure_ev for frame, _image in selected)[len(selected) // 2]
    normalized = []
    for frame, image in selected:
        scale = 2 ** max(-3.0, min(3.0, reference_ev - frame.exposure_ev))
        lookup = [min(255, round(value * scale)) for value in range(256)]
        normalized.append(image.point(lookup * 3))
    fused = normalized[0]
    for index, image in enumerate(normalized[1:], start=2):
        fused = Image.blend(fused, image, 1.0 / index)
    return ExposureFusion(
        _encode_png(fused),
        tuple(frame.relative_path for frame, _image in selected),
    )


# {
#   責務: [_encode_png: RGB Pillow pixelsをPNG bytesへ変換する]
#   処理: [serialize a deterministic local candidate image]
#   引数: [image: RGB pixels]
#   戻り値: [bytes: encoded PNG]
# }
def _encode_png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


# {
#   責務: [_interframe_difference: capture frames間の低解像度pixel差を測る]
#   処理: [estimate capture diversity without claiming camera-motion registration]
#   引数: [images: decoded RGB frame sequence]
#   戻り値: [float | None: normalized mean difference, absent for one frame]
# }
def _interframe_difference(images) -> float | None:
    if len(images) < 2:
        return None
    thumbnails = [
        image.convert("L").resize((64, 64), Image.Resampling.BILINEAR) for image in images
    ]
    differences = [
        sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / (255 * 1)
        for first, second in zip(thumbnails, thumbnails[1:], strict=False)
    ]
    return sum(differences) / len(differences)
