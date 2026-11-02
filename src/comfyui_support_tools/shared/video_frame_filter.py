"""Analyze normalized video frames and report conservative keep/drop/review decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from comfyui_support_tools.shared.contracts.frame_analysis import (
    FrameAnalysisInput,
    FrameDecodeStatus,
)
from comfyui_support_tools.shared.contracts.frame_filter import (
    FrameFilterAction,
    FrameFilterBatchManifest,
    FrameFilterDecision,
    FrameFilterOptions,
    FrameFilterPreset,
    FrameFilterReport,
    FrameTextBox,
)


# {
#   責務: [_FrameFeatures: low-cost frame metricsを一時的に保持する]
#   フィールド: [luminance、detail、text、temporalに使うhistogram]
# }
@dataclass(frozen=True)
class _FrameFeatures:
    mean_luminance: float
    black_ratio: float
    white_ratio: float
    entropy: float
    edge_density: float
    sharpness: float
    local_contrast: float
    non_text_information: float
    text_area_ratio: float
    title_card_score: float
    credits_score: float
    histogram: tuple[float, ...]


# {
#   責務: [analyze_frame_sequence: normalized frame sequenceをcheap CVでfilter reportへ変換する]
#   処理: [1: options/OCR evidenceを検証する 2: 各frameの特徴を抽出する 3: 時系列evidenceとdecisionを融合する]
#   引数: [source_id: source identity, frames: normalized frames, options: per-run options, text_boxes: optional OCR evidence, subject_scores/saliency_scores: optional analyzer scores]
#   戻り値: [FrameFilterBatchManifest: per-frame reports/counts]
# }
def analyze_frame_sequence(
    source_id: str,
    frames: Sequence[FrameAnalysisInput],
    options: FrameFilterOptions | None = None,
    *,
    text_boxes: Mapping[int, Sequence[FrameTextBox]] | None = None,
    subject_scores: Mapping[int, float] | None = None,
    saliency_scores: Mapping[int, float] | None = None,
) -> FrameFilterBatchManifest:
    options = options or FrameFilterOptions()
    _validate_options(source_id, options, text_boxes, subject_scores, saliency_scores)
    resolved_preset = FrameFilterPreset(options.preset)
    if not frames:
        raise ValueError("at least one normalized frame is required")
    if any(
        index >= len(frames)
        for mapping in (text_boxes or {}, subject_scores or {}, saliency_scores or {})
        for index in mapping
    ):
        raise ValueError("analyzer evidence references a frame outside the sequence")
    boxes_by_frame = text_boxes or {}
    subjects = subject_scores or {}
    saliency = saliency_scores or {}
    if options.enabled and (options.detect_text_only or options.detect_title_credits):
        if text_boxes is None:
            raise ValueError("OCR evidence is required when text-only or title rules are enabled")
    if not options.enabled:
        reports = tuple(
            _disabled_report(index, frame, options.analyzer_version)
            for index, frame in enumerate(frames)
        )
        return FrameFilterBatchManifest(
            source_id,
            options,
            reports,
            sum(item.decision is FrameFilterDecision.KEEP for item in reports),
            0,
            0,
            sum(item.decision is FrameFilterDecision.ERROR for item in reports),
        )
    features = tuple(
        _extract_features(frame, tuple(boxes_by_frame.get(index, ())))
        if frame.has_pixels and frame.decode_status is FrameDecodeStatus.OK
        else None
        for index, frame in enumerate(frames)
    )
    reports = tuple(
        _build_report(
            index,
            frame,
            features,
            frames,
            options,
            resolved_preset,
            tuple(boxes_by_frame.get(index, ())),
            subjects.get(index),
            saliency.get(index),
        )
        for index, frame in enumerate(frames)
    )
    return FrameFilterBatchManifest(
        source_id,
        options,
        reports,
        sum(item.decision is FrameFilterDecision.KEEP for item in reports),
        sum(item.decision is FrameFilterDecision.DROP for item in reports),
        sum(item.decision is FrameFilterDecision.REVIEW for item in reports),
        sum(item.decision is FrameFilterDecision.ERROR for item in reports),
    )


# {
#   責務: [_extract_features: canonical luminance planeから単一frameの低コストmetricsを算出する]
#   処理: [1: active picture rectを適用する 2: histogram/edge/sharpness/text featuresを計算する]
#   引数: [frame: normalized frame, text_boxes: optional normalized OCR boxes]
#   戻り値: [_FrameFeatures: filter evidence]
# }
def _extract_features(
    frame: FrameAnalysisInput, text_boxes: tuple[FrameTextBox, ...]
) -> _FrameFeatures:
    assert frame.luminance is not None
    luminance = frame.luminance
    rect = frame.active_picture_rect
    if rect is not None:
        luminance = luminance[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
    if luminance.size == 0 or not np.isfinite(luminance).all():
        raise ValueError("normalized frame luminance is empty or non-finite")
    values = np.clip(luminance, 0.0, 1.0).astype(np.float32, copy=False)
    histogram, _edges = np.histogram(values, bins=32, range=(0.0, 1.0))
    probability = histogram.astype(np.float64) / max(1, values.size)
    nonzero = probability[probability > 0]
    entropy = float(-(nonzero * np.log2(nonzero)).sum() / math.log2(32))
    gradient_x = np.diff(values, axis=1) if values.shape[1] > 1 else np.zeros_like(values)
    gradient_y = np.diff(values, axis=0) if values.shape[0] > 1 else np.zeros_like(values)
    edge_density = float(
        (
            np.count_nonzero(np.abs(gradient_x) > 0.012)
            + np.count_nonzero(np.abs(gradient_y) > 0.012)
        )
        / max(1, gradient_x.size + gradient_y.size)
    )
    if min(values.shape) >= 3:
        center = values[1:-1, 1:-1]
        laplacian = (
            values[:-2, 1:-1]
            + values[2:, 1:-1]
            + values[1:-1, :-2]
            + values[1:-1, 2:]
            - 4.0 * center
        )
        sharpness = float(np.var(laplacian, dtype=np.float64))
    else:
        sharpness = 0.0
    text_area = min(1.0, sum(_box_area(box) for box in text_boxes))
    non_text_information = max(entropy, min(1.0, edge_density * 8.0))
    line_count = len(text_boxes)
    text_confidence = sum(box.confidence for box in text_boxes) / line_count if line_count else 0.0
    centered_text = any(0.2 <= box.y + box.height / 2 <= 0.8 for box in text_boxes)
    title_card = (
        min(1.0, 1.0 - non_text_information) * min(1.0, line_count) * text_confidence
        if centered_text and 0 < line_count < 4
        else 0.0
    )
    credits = (
        min(1.0, 1.0 - non_text_information) * min(1.0, line_count / 8.0) * text_confidence
        if line_count >= 4
        else 0.0
    )
    return _FrameFeatures(
        float(values.mean()),
        float(np.count_nonzero(values <= 0.025) / values.size),
        float(np.count_nonzero(values >= 0.98) / values.size),
        entropy,
        edge_density,
        sharpness,
        float(values.std()),
        non_text_information,
        text_area,
        title_card,
        credits,
        tuple(float(item) for item in probability),
    )


# {
#   責務: [_build_report: visual/temporal evidenceをconfidence thresholdへ統合する]
#   処理: [1: decode resultを分離する 2: categoriesをscore化する 3: title policyとpresetでdecisionする]
#   引数: [index/frame/features/frames/options/preset/text/optional scores]
#   戻り値: [FrameFilterReport: decisionとexplanation]
# }
def _build_report(
    index: int,
    frame: FrameAnalysisInput,
    features: tuple[_FrameFeatures | None, ...],
    frames: Sequence[FrameAnalysisInput],
    options: FrameFilterOptions,
    preset: FrameFilterPreset,
    text_boxes: tuple[FrameTextBox, ...],
    subject_score: float | None,
    saliency_score: float | None,
) -> FrameFilterReport:
    timestamp = frame.actual_timestamp
    provenance = (
        ("analyzer", options.analyzer_version),
        ("preset", preset.value),
        ("source_colorspace", frame.canonical_colorspace),
    )
    feature = features[index]
    if feature is None:
        return _empty_report(
            index,
            timestamp,
            FrameFilterDecision.ERROR,
            (f"decode:{frame.decode_status.value}",),
            provenance,
        )
    thresholds = _preset_thresholds(preset, options)
    previous = features[index - 1] if index > 0 else None
    following = features[index + 1] if index + 1 < len(features) else None
    neighbors = tuple(item for item in (previous, following) if item is not None)
    neighbor_similarity = _neighbor_similarity(feature, neighbors) if neighbors else None
    transition_score = (
        _transition_score(feature, previous, following) if options.compare_neighbors else 0.0
    )
    reasons: list[str] = []
    scores: list[float] = []
    black_score = _extreme_score(
        feature.black_ratio, feature.entropy, feature.edge_density, thresholds
    )
    white_score = _extreme_score(
        feature.white_ratio, feature.entropy, feature.edge_density, thresholds
    )
    if options.detect_black and black_score >= thresholds["candidate"]:
        reasons.append("near_black_low_structure")
        scores.append(black_score)
    if options.detect_white and white_score >= thresholds["candidate"]:
        reasons.append("near_white_low_structure")
        scores.append(white_score)
    low_detail_score = max(0.0, 1.0 - feature.entropy) * max(
        0.0, 1.0 - min(1.0, feature.edge_density * 8)
    )
    if options.detect_low_detail and low_detail_score >= thresholds["candidate"]:
        reasons.append("low_detail")
        scores.append(low_detail_score)
    text_only_score = _text_only_score(feature, text_boxes, subject_score)
    if options.detect_text_only and text_only_score >= thresholds["candidate"]:
        reasons.append("text_only_low_visual_information")
        scores.append(text_only_score)
    title_score = max(feature.title_card_score, feature.credits_score)
    if options.detect_title_credits and title_score >= thresholds["title"]:
        label = "credits" if feature.credits_score >= feature.title_card_score else "title_card"
        reasons.append(label)
        scores.append(title_score)
    if options.detect_transition and transition_score >= thresholds["candidate"]:
        reasons.append("fade_or_transition")
        scores.append(transition_score)
    blur_score = _blur_outlier_score(feature, neighbors)
    if options.detect_blur and blur_score >= thresholds["candidate"]:
        reasons.append("blurred_outlier")
        scores.append(blur_score)

    information_protection = max(
        subject_score or 0.0,
        saliency_score or 0.0,
        min(1.0, feature.edge_density * 12.0),
        min(1.0, feature.entropy * 1.6),
    )
    low_information_score = max(scores, default=0.0)
    confidence = low_information_score * (1.0 - 0.55 * information_protection)
    if not reasons:
        decision = FrameFilterDecision.KEEP
        reasons.append("visual_information_present")
    elif (
        confidence < options.low_confidence_threshold
        or information_protection >= thresholds["protect"]
    ):
        decision = FrameFilterDecision.KEEP
        reasons.append("meaningful_structure_protected")
    elif confidence >= options.high_confidence_threshold:
        decision = FrameFilterDecision.DROP
    else:
        decision = FrameFilterDecision.REVIEW

    if title_score >= thresholds["title"] and options.detect_title_credits:
        policy = options.title_credits_policy
        if policy == "keep":
            decision = FrameFilterDecision.KEEP
            reasons.append("title_credits_policy_keep")
        elif policy == "drop":
            decision = FrameFilterDecision.DROP
            reasons.append("title_credits_policy_drop")
        else:
            decision = FrameFilterDecision.REVIEW
            reasons.append("title_credits_policy_separate")

    return _feature_report(
        index,
        frame,
        feature,
        decision,
        tuple(dict.fromkeys(reasons)),
        low_information_score,
        confidence,
        neighbor_similarity,
        transition_score,
        title_score,
        subject_score,
        saliency_score,
        provenance,
    )


# {
#   責務: [_feature_report: computed metricsをimmutable report schemaへ格納する]
#   処理: [1: category scoresとtemporal valuesを整形する 2: complete provenanceを記録する]
#   引数: [index/frame/features/decision/reasons/confidence/optional metrics]
#   戻り値: [FrameFilterReport]
# }
def _feature_report(
    index: int,
    frame: FrameAnalysisInput,
    feature: _FrameFeatures,
    decision: FrameFilterDecision,
    reasons: tuple[str, ...],
    low_information_score: float,
    confidence: float,
    neighbor_similarity: float | None,
    transition_score: float | None,
    title_score: float,
    subject_score: float | None,
    saliency_score: float | None,
    provenance: tuple[tuple[str, str], ...],
) -> FrameFilterReport:
    return FrameFilterReport(
        index,
        frame.actual_timestamp,
        feature.mean_luminance,
        feature.black_ratio,
        feature.white_ratio,
        feature.entropy,
        feature.edge_density,
        feature.sharpness,
        feature.text_area_ratio,
        feature.non_text_information,
        subject_score,
        saliency_score,
        neighbor_similarity,
        transition_score,
        feature.title_card_score,
        feature.credits_score,
        low_information_score,
        decision,
        reasons,
        confidence,
        provenance
        + (
            ("title_card_score", f"{feature.title_card_score:.6f}"),
            ("credits_score", f"{feature.credits_score:.6f}"),
        ),
    )


# {
#   責務: [_empty_report: decode失敗を低情報判定と分けたerror reportにする]
#   処理: [1: pixel metricsを空欄にする 2: explicit decode reasonを保持する]
#   引数: [index/timestamp/decision/reasons/provenance]
#   戻り値: [FrameFilterReport]
# }
def _empty_report(
    index: int,
    timestamp: float | None,
    decision: FrameFilterDecision,
    reasons: tuple[str, ...],
    provenance: tuple[tuple[str, str], ...],
) -> FrameFilterReport:
    return FrameFilterReport(
        index,
        timestamp,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0.0,
        decision,
        reasons,
        1.0,
        provenance,
    )


# {
#   責務: [_disabled_report: filter OFF時はmetricsを計算せず既定keep/error結果を作る]
#   処理: [1: decode contractを確認する 2: valid frameをfilter_disabled keepにする]
#   引数: [index: position, frame: normalized frame, analyzer_version: provenance]
#   戻り値: [FrameFilterReport: no-analysis result]
# }
def _disabled_report(
    index: int, frame: FrameAnalysisInput, analyzer_version: str
) -> FrameFilterReport:
    if not frame.has_pixels or frame.decode_status is not FrameDecodeStatus.OK:
        return _empty_report(
            index,
            frame.actual_timestamp,
            FrameFilterDecision.ERROR,
            (f"decode:{frame.decode_status.value}",),
            (("analyzer", analyzer_version),),
        )
    return _empty_report(
        index,
        frame.actual_timestamp,
        FrameFilterDecision.KEEP,
        ("filter_disabled",),
        (("analyzer", analyzer_version),),
    )


# {
#   責務: [_text_only_score: OCR bboxとnon-text metricsを使い文字だけのframe候補をscore化する]
#   処理: [1: OCR text extentを確認する 2: non-text detail/subject情報が少ない場合だけscoreを返す]
#   引数: [features: image metrics, text_boxes: OCR evidence, subject_score: optional detector evidence]
#   戻り値: [score: text-only candidate confidence]
# }
def _text_only_score(
    features: _FrameFeatures, text_boxes: tuple[FrameTextBox, ...], subject_score: float | None
) -> float:
    if not text_boxes:
        return 0.0
    non_text = max(features.non_text_information, subject_score or 0.0)
    text_extent = min(1.0, sum(_box_area(box) for box in text_boxes))
    detection_confidence = sum(box.confidence for box in text_boxes) / len(text_boxes)
    return max(0.0, 1.0 - non_text) * max(0.0, 1.0 - 0.5 * text_extent) * detection_confidence


# {
#   責務: [_extreme_score: black/white ratioとdetailを融合してblank候補をscore化する]
#   処理: [1: luminance極端比率を確認する 2: entropy/edge evidenceで構造を保護する]
#   引数: [extreme_ratio/entropy/edge_density/preset thresholds]
#   戻り値: [candidate score]
# }
def _extreme_score(
    extreme_ratio: float, entropy: float, edge_density: float, thresholds: Mapping[str, float]
) -> float:
    if extreme_ratio < thresholds["extreme_ratio"]:
        return 0.0
    structure = min(1.0, entropy * 2.0 + edge_density * 8.0)
    return min(1.0, extreme_ratio * (1.0 - 0.8 * structure))


# {
#   責務: [_transition_score: 前後frameが有情報で中央のみ空白に近いfade候補を評価する]
#   処理: [1: 両隣があることを確認する 2: luma/entropy差とcurrent低detailを融合する]
#   引数: [current/previous/following features]
#   戻り値: [transition confidence]
# }
def _transition_score(
    current: _FrameFeatures,
    previous: _FrameFeatures | None,
    following: _FrameFeatures | None,
) -> float:
    if previous is None or following is None:
        return 0.0
    neighbors_have_content = min(previous.entropy, following.entropy) >= 0.12
    if not neighbors_have_content:
        return 0.0
    bridge = max(
        abs(current.mean_luminance - previous.mean_luminance),
        abs(current.mean_luminance - following.mean_luminance),
    )
    empty = max(current.black_ratio, current.white_ratio, 1.0 - current.entropy)
    return min(1.0, max(0.0, (bridge - 0.04) * 3.2) * empty)


# {
#   責務: [_blur_outlier_score: neighborより極端にsharpnessが低いframeのみblur候補にする]
#   処理: [1: neighboring sharpness baselineを計算する 2: relative blur gapを返す]
#   引数: [current: current metrics, neighbors: available adjacent metrics]
#   戻り値: [relative blur score]
# }
def _blur_outlier_score(current: _FrameFeatures, neighbors: tuple[_FrameFeatures, ...]) -> float:
    if (
        not neighbors
        or current.black_ratio >= 0.8
        or current.white_ratio >= 0.8
        or current.entropy < 0.12
    ):
        return 0.0
    baseline = float(np.median([item.sharpness for item in neighbors]))
    if baseline < 1e-5 or current.sharpness >= baseline * 0.2:
        return 0.0
    return min(1.0, 1.0 - current.sharpness / baseline)


# {
#   責務: [_neighbor_similarity: neighbor histogramから類似度の上限を計算する]
#   処理: [1: current/neighbor histogramへcosine similarityを適用する 2: max similarityを返す]
#   引数: [current: current feature, neighbors: neighboring features]
#   戻り値: [similarity: 0..1 or None]
# }
def _neighbor_similarity(
    current: _FrameFeatures, neighbors: tuple[_FrameFeatures, ...]
) -> float | None:
    similarities = []
    left = np.asarray(current.histogram, dtype=np.float64)
    for neighbor in neighbors:
        right = np.asarray(neighbor.histogram, dtype=np.float64)
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        similarities.append(float(np.dot(left, right) / denominator) if denominator else 0.0)
    return max(similarities, default=None)


# {
#   責務: [_box_area: normalized OCR box geometryの安全なareaを返す]
#   処理: [1: width/heightの負値をclampする 2: normalized areaを計算する]
#   引数: [box: OCR bounding box]
#   戻り値: [normalized area]
# }
def _box_area(box: FrameTextBox) -> float:
    return max(0.0, box.width) * max(0.0, box.height)


# {
#   責務: [_preset_thresholds: presetごとのdecision bandを返す]
#   処理: [1: conservative/balanced/aggressive thresholdを解決する]
#   引数: [preset: selected preset]
#   戻り値: [threshold map]
# }
def _preset_thresholds(preset: FrameFilterPreset, options: FrameFilterOptions) -> dict[str, float]:
    if preset is FrameFilterPreset.CONSERVATIVE:
        return {"extreme_ratio": 0.995, "candidate": 0.86, "title": 0.9, "protect": 0.08}
    if preset is FrameFilterPreset.BALANCED:
        return {"extreme_ratio": 0.98, "candidate": 0.72, "title": 0.78, "protect": 0.15}
    if preset is FrameFilterPreset.AGGRESSIVE:
        return {"extreme_ratio": 0.92, "candidate": 0.55, "title": 0.65, "protect": 0.22}
    return {
        "extreme_ratio": options.custom_extreme_ratio_threshold,
        "candidate": options.custom_candidate_threshold,
        "title": options.custom_title_threshold,
        "protect": options.custom_information_protection_threshold,
    }


# {
#   責務: [_validate_options: filter configurationとoptional analyzer evidenceを検証する]
#   処理: [1: source/purpose/policy/thresholdを検査する 2: optional scores/text boxを範囲検証する]
#   引数: [source_id/options/optional OCR and detector scores]
#   戻り値: []
# }
def _validate_options(
    source_id: str,
    options: FrameFilterOptions,
    text_boxes: Mapping[int, Sequence[FrameTextBox]] | None,
    subject_scores: Mapping[int, float] | None,
    saliency_scores: Mapping[int, float] | None,
) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be non-empty")
    if not isinstance(options, FrameFilterOptions):
        raise ValueError("options must be a FrameFilterOptions instance")
    try:
        FrameFilterPreset(options.preset)
    except (TypeError, ValueError) as error:
        raise ValueError("unsupported frame filter preset") from error
    try:
        FrameFilterAction(options.action)
    except (TypeError, ValueError) as error:
        raise ValueError("unsupported frame filter action") from error
    if not isinstance(options.title_credits_policy, str) or options.title_credits_policy not in {
        "keep",
        "drop",
        "separate",
    }:
        raise ValueError("title_credits_policy must be keep, drop, or separate")
    bool_fields = (
        options.enabled,
        options.detect_black,
        options.detect_white,
        options.detect_transition,
        options.detect_text_only,
        options.detect_title_credits,
        options.detect_low_detail,
        options.detect_blur,
        options.compare_neighbors,
    )
    if not all(type(value) is bool for value in bool_fields):
        raise ValueError("frame filter switches must be booleans")
    thresholds = (
        options.low_confidence_threshold,
        options.high_confidence_threshold,
        options.custom_extreme_ratio_threshold,
        options.custom_candidate_threshold,
        options.custom_title_threshold,
        options.custom_information_protection_threshold,
    )
    if (
        not isinstance(options.purpose, str)
        or not isinstance(options.analyzer_version, str)
        or not options.purpose.strip()
        or not options.analyzer_version.strip()
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in thresholds
        )
        or not 0 <= options.low_confidence_threshold <= options.high_confidence_threshold <= 1
        or any(
            not math.isfinite(value) or not 0 <= value <= 1
            for value in (
                options.custom_extreme_ratio_threshold,
                options.custom_candidate_threshold,
                options.custom_title_threshold,
                options.custom_information_protection_threshold,
            )
        )
    ):
        raise ValueError("invalid frame filter thresholds or provenance")
    for score_map in (subject_scores, saliency_scores):
        if score_map is not None and not isinstance(score_map, Mapping):
            raise ValueError("subject and saliency scores must be mappings")
    for score_map in (subject_scores or {}, saliency_scores or {}):
        if any(
            type(index) is not int
            or index < 0
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
            for index, score in score_map.items()
        ):
            raise ValueError("subject and saliency scores must be finite values in 0..1")
    if text_boxes is not None and not isinstance(text_boxes, Mapping):
        raise ValueError("OCR boxes must be a mapping by frame index")
    for index, boxes in (text_boxes or {}).items():
        if (
            type(index) is not int
            or index < 0
            or not isinstance(boxes, Sequence)
            or isinstance(boxes, (str, bytes))
        ):
            raise ValueError("OCR box entries must use nonnegative integer frame indexes")
        for box in boxes:
            if not isinstance(box, FrameTextBox):
                raise ValueError("OCR boxes must contain FrameTextBox values")
            numeric = (box.x, box.y, box.width, box.height, box.confidence)
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in numeric
            ) or not isinstance(box.text, str):
                raise ValueError("OCR boxes must contain finite normalized geometry")
            if (
                box.x < 0
                or box.y < 0
                or box.width <= 0
                or box.height <= 0
                or box.x + box.width > 1
                or box.y + box.height > 1
                or not 0 <= box.confidence <= 1
            ):
                raise ValueError("OCR boxes must remain within normalized frame bounds")
