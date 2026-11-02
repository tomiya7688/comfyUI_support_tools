"""Pillow-based, evidence-aware weak-signal processing methods and mode priors."""

from __future__ import annotations

import io
from statistics import fmean

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageMath, ImageOps, ImageStat

from .contracts import (
    EvidenceKind,
    EvidenceProvenance,
    ObservationInput,
    WeakSignalCandidate,
    WeakSignalMode,
    WeakSignalRequest,
)


# {
#   責務: [PillowWeakSignalBackend: conservative classical weak-signal candidatesを生成する]
#   フィールド: [mode-specific contrast priors, multi-frame median layer separation]
#   処理: [return natural/conservative/task-enhanced candidates with explicit inference provenance]
# }
class PillowWeakSignalBackend:
    # {
    #   責務: [supported_modes: built-in classical backendが提供するmodeを列挙する]
    #   処理: [exclude AUTO because application-level mode classification owns that value]
    #   引数: [self: Pillow backend]
    #   戻り値: [frozenset[WeakSignalMode]: declared task modes]
    # }
    @property
    def supported_modes(self) -> frozenset[WeakSignalMode]:
        return frozenset(
            mode
            for mode in WeakSignalMode
            if mode not in {WeakSignalMode.AUTO, WeakSignalMode.TRANSLUCENT_SURFACE}
        )

    # {
    #   責務: [generate: observation/modeから比較可能なcandidate setを作成する]
    #   処理: [decode bounded frames, apply mode-specific classical prior, preserve observed/inferred notes, rank by named task metric]
    #   引数: [observation: encoded image/burst/video frames, request: strength/count/alignment, mode: resolved task]
    #   戻り値: [tuple[WeakSignalCandidate, ...]: best-first task candidates]
    #   エラー: [TypeError or ValueError: invalid frame/mode or insufficient aligned samples]
    # }
    def generate(
        self,
        observation: ObservationInput,
        request: WeakSignalRequest,
        mode: WeakSignalMode,
    ) -> tuple[WeakSignalCandidate, ...]:
        if mode is WeakSignalMode.AUTO:
            raise ValueError("backend requires a resolved weak-signal mode")
        if mode not in self.supported_modes:
            raise LookupError(f"Pillow backend does not support {mode.value}")
        frames = tuple(_decode_rgb(payload) for payload in observation.frames)
        observed_frames = frames
        size = frames[0].size
        if any(frame.size != size for frame in frames):
            raise ValueError("all observation frames must share the same dimensions")
        if size[0] * size[1] > 16_000_000:
            raise ValueError("weak-signal frame exceeds the 16-megapixel processing budget")
        component_frames = ()
        provenance_note = "single-frame enhancement; no hidden content is recovered"
        confidence_base = 0.45
        if mode is WeakSignalMode.REFLECTION:
            if len(frames) >= 3 and observation.media_kind in {"burst", "video"}:
                if not request.aligned_frames_assumed:
                    raise ValueError(
                        "multi-frame reflection separation requires an alignment declaration"
                    )
                stable, residuals = _fuse_transient_reflections(frames)
                frames = stable
                component_frames = (("transient_reflection_residual", residuals),)
                provenance_note = (
                    "aligned-frame temporal median preserves temporally stable scene content; "
                    "moving reflections are residual candidates, while static reflections remain ambiguous"
                )
                confidence_base = 0.72
            else:
                provenance_note = "single-image reflection/transmission is underdetermined; this is a contrast candidate, not physical layer recovery"
        variants = _make_variants(frames, mode, request.strength)
        candidate_values = []
        for _index, (label, variant_frames, strength) in enumerate(
            variants[: request.candidate_count]
        ):
            encoded = tuple(_encode_png(frame) for frame in variant_frames)
            scores = _score_frames(frames, variant_frames)
            confidence = min(0.95, max(0.05, confidence_base * (1 - 0.25 * strength)))
            provenance = [
                EvidenceProvenance(
                    "input observation",
                    EvidenceKind.OBSERVED,
                    1.0,
                    "source_observation",
                    "original encoded pixels are preserved in the observed_input component",
                ),
                EvidenceProvenance(
                    "output image",
                    EvidenceKind.ENHANCED,
                    confidence,
                    "pillow_classical_v1",
                    provenance_note,
                ),
            ]
            original_frames = tuple(_encode_png(frame) for frame in observed_frames)
            components = (("observed_input", original_frames), ("transmission_candidate", encoded))
            if component_frames:
                residual_encoded = tuple(_encode_png(frame) for frame in component_frames[0][1])
                components += ((component_frames[0][0], residual_encoded),)
                provenance.append(
                    EvidenceProvenance(
                        component_frames[0][0],
                        EvidenceKind.INFERRED,
                        confidence_base,
                        "aligned_temporal_median_v1",
                        "absolute temporal residual includes scene motion and noise; it is not a verified reflection mask",
                    )
                )
            candidate_values.append(
                WeakSignalCandidate(
                    f"{mode.value}:{label}",
                    mode,
                    encoded,
                    tuple(provenance),
                    confidence,
                    "pillow_classical_v1",
                    strength,
                    tuple(sorted(scores.items())),
                    components,
                )
            )
        return tuple(sorted(candidate_values, key=lambda item: _rank_key(mode, item)))


# {
#   責務: [_decode_rgb: encoded image frameをbounded RGBへdecodeする]
#   処理: [reject invalid and oversized inputs before mode algorithms allocate intermediates]
#   引数: [payload: encoded observation frame]
#   戻り値: [Image.Image: decoded RGB frame]
# }
def _decode_rgb(payload: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            if image.width < 1 or image.height < 1 or image.width * image.height > 16_000_000:
                raise ValueError("weak-signal image dimensions exceed processing limits")
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("observation frame is not a valid safe-to-decode image") from error


# {
#   責務: [_make_variants: resolved mode-specific priorから3つのprocessing strength候補を作る]
#   処理: [produce conservative, natural and enhanced candidates while keeping original signal visible]
#   引数: [frames: decoded observation, mode: task prior, strength: user processing amount]
#   戻り値: [tuple: label, output frames and applied strength]
# }
def _make_variants(frames, mode: WeakSignalMode, strength: float):
    strengths = (max(0.1, strength * 0.5), max(0.1, strength), min(1.0, max(0.1, strength * 1.5)))
    output = []
    for label, amount in zip(("conservative", "natural", "enhanced"), strengths, strict=True):
        result = tuple(_process_frame(frame, mode, amount) for frame in frames)
        output.append((label, result, amount))
    return tuple(output)


# {
#   責務: [_process_frame: one mode-specific classical image priorを適用する]
#   処理: [use local background normalization, highlight suppression, dehaze contrast or detail enhancement]
#   引数: [image: source observation, mode: selected low-level task, strength: processing amount]
#   戻り値: [Image.Image: enhanced candidate frame]
# }
def _process_frame(image: Image.Image, mode: WeakSignalMode, strength: float) -> Image.Image:
    if mode in {WeakSignalMode.PAPER_SHOWTHROUGH, WeakSignalMode.UNEVEN_ILLUMINATION}:
        radius = max(2, min(image.size) // 24)
        background = image.filter(ImageFilter.GaussianBlur(radius=radius))
        normalized = ImageChops.divide(image, background, scale=220)
        normalized = ImageOps.autocontrast(normalized, cutoff=(0.3 * strength, 0.3 * strength))
        return Image.blend(image, normalized, strength * 0.7)
    if mode is WeakSignalMode.GLARE:
        luminance = ImageOps.grayscale(image)
        highlight_mask = luminance.point(lambda value: 255 if value >= 220 else 0)
        highlight_mask = highlight_mask.filter(ImageFilter.GaussianBlur(radius=2))
        softened = image.filter(ImageFilter.GaussianBlur(radius=max(1, min(image.size) // 96)))
        reduced = Image.composite(softened, image, highlight_mask)
        return Image.blend(image, reduced, strength)
    if mode is WeakSignalMode.VEIL:
        dehazed = ImageOps.autocontrast(image, cutoff=(strength * 1.2, strength * 0.6))
        return Image.blend(image, dehazed, strength)
    if mode in {WeakSignalMode.WEAK_DETAIL, WeakSignalMode.REFLECTION}:
        contrasted = ImageOps.autocontrast(image, cutoff=(strength * 0.5, strength * 0.5))
        sharpened = ImageEnhance.Sharpness(contrasted).enhance(1 + strength * 1.5)
        return Image.blend(image, sharpened, strength)
    raise LookupError(f"no Pillow prior is implemented for {mode.value}")


# {
#   責務: [_fuse_transient_reflections: aligned burst/videoからtemporal median transmission候補を推定する]
#   処理: [3-frame median windows suppress moving transient overlays and emit absolute residual components]
#   引数: [frames: same-sized aligned RGB sequence]
#   戻り値: [tuple: stable transmission candidate sequence, inferred transient residual sequence]
# }
def _fuse_transient_reflections(frames: tuple[Image.Image, ...]):
    if len(frames) < 3:
        raise ValueError("temporal reflection fusion requires at least three frames")
    stable_frames = []
    residuals = []
    for index, current in enumerate(frames):
        previous = frames[max(0, index - 1)]
        following = frames[min(len(frames) - 1, index + 1)]
        stable = _median_three(previous, current, following)
        stable_frames.append(stable)
        residuals.append(ImageChops.difference(current, stable))
    return tuple(stable_frames), tuple(residuals)


# {
#   責務: [_median_three: three aligned 8-bit RGB samplesのper-pixel medianを計算する]
#   処理: [compute per-channel median without creating hallucinated high-frequency pixels]
#   引数: [first/second/third: aligned same-sized RGB frames]
#   戻り値: [Image.Image: temporal median frame]
# }
def _median_three(first: Image.Image, second: Image.Image, third: Image.Image) -> Image.Image:
    channels = []
    for a, b, c in zip(first.split(), second.split(), third.split(), strict=True):
        median = ImageMath.lambda_eval(
            lambda values: max(
                min(values["a"], values["b"]), min(max(values["a"], values["b"]), values["c"])
            ),
            a=a,
            b=b,
            c=c,
        )
        channels.append(median.convert("L"))
    return Image.merge("RGB", tuple(channels))


# {
#   責務: [_score_frames: named contrast and structure proxiesをcandidateへ付与する]
#   処理: [report mode-agnostic measurements as separate dimensions, never as a universal truth score]
#   引数: [source: input frames, candidate: enhanced frames]
#   戻り値: [dict[str, float]: local_contrast_proxy and structure_retention]
# }
def _score_frames(source, candidate) -> dict[str, float]:
    contrasts = []
    retention = []
    for original, enhanced in zip(source, candidate, strict=True):
        contrasts.append(min(1.0, fmean(ImageStat.Stat(enhanced.convert("L")).stddev) / 127.5))
        difference = ImageChops.difference(original, enhanced)
        mean_difference = fmean(ImageStat.Stat(difference).mean) / 255
        retention.append(max(0.0, 1.0 - mean_difference))
    return {
        "local_contrast_proxy": fmean(contrasts),
        "structure_retention": fmean(retention),
    }


# {
#   責務: [_rank_key: mode-specific interpretable ranking objectiveを作る]
#   処理: [trade off named contrast proxy against observed structure retention per task prior]
#   引数: [mode: resolved task, candidate: measured candidate dimensions]
#   戻り値: [tuple[float, str]: stable candidate ordering]
# }
def _rank_key(mode: WeakSignalMode, candidate: WeakSignalCandidate) -> tuple[float, str]:
    scores = dict(candidate.scores)
    contrast = scores.get("local_contrast_proxy", 0)
    retention = scores.get("structure_retention", 0)
    contrast_weight = (
        0.35 if mode in {WeakSignalMode.WEAK_DETAIL, WeakSignalMode.PAPER_SHOWTHROUGH} else 0.2
    )
    utility = (1 - contrast_weight) * retention + contrast_weight * contrast
    return -utility, candidate.candidate_id


# {
#   責務: [_encode_png: PIL candidate frameをmetadata/adapter用PNG bytesへ変換する]
#   処理: [serialize deterministic RGB PNG without altering input evidence]
#   引数: [image: candidate RGB frame]
#   戻り値: [bytes: encoded PNG frame]
# }
def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# {
#   責務: [classify_weak_signal_mode: image statisticsからmode priorとconfidenceを推定する]
#   処理: [use bounded brightness/chroma/contrast heuristics and return rationale instead of claiming semantic recognition]
#   引数: [observation: encoded image or sequence]
#   戻り値: [tuple[WeakSignalMode, float, str]: suggested task and heuristic confidence]
# }
def classify_weak_signal_mode(observation: ObservationInput) -> tuple[WeakSignalMode, float, str]:
    frame = _decode_rgb(observation.frames[0])
    grayscale = ImageOps.grayscale(frame)
    mean = ImageStat.Stat(grayscale).mean[0]
    deviation = ImageStat.Stat(grayscale).stddev[0]
    histogram = grayscale.histogram()
    clipped = sum(histogram[245:]) / max(frame.width * frame.height, 1)
    if observation.media_kind in {"burst", "video"} and len(observation.frames) >= 3:
        return (
            WeakSignalMode.REFLECTION,
            0.66,
            "multi-frame input can support temporal residual analysis",
        )
    if clipped >= 0.18:
        return WeakSignalMode.GLARE, 0.58, "large bright-region histogram suggests a glare prior"
    if mean >= 175 and deviation >= 25:
        return (
            WeakSignalMode.PAPER_SHOWTHROUGH,
            0.46,
            "bright low-chroma document-like prior; verify manually",
        )
    return WeakSignalMode.WEAK_DETAIL, 0.4, "generic weak-detail prior; semantic mode is uncertain"
