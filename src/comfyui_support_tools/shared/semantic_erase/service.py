"""Non-destructive semantic erase orchestration and folder batch mode."""

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from comfyui_support_tools.shared.semantic_erase.backends import (
    InpaintBackendRegistry,
    InpaintResult,
    create_default_backend_registry,
    mask_variants,
)
from comfyui_support_tools.shared.semantic_erase.contracts import (
    MAX_IMAGE_PIXELS,
    BatchStatus,
    EraseBatchItem,
    EraseMode,
    EraseRequest,
    EraseResult,
    EraseTargetType,
    MatchPolicy,
    QualityProfile,
    RegionCandidate,
    SemanticEraseTarget,
)
from comfyui_support_tools.shared.semantic_erase.evaluator import (
    evaluate_candidate,
    make_retry_masks,
)
from comfyui_support_tools.shared.semantic_erase.history import (
    EraseHistoryStore,
    source_sha256,
)
from comfyui_support_tools.shared.semantic_erase.providers import (
    RegionProviderRegistry,
    resolve_region_candidates,
)
from comfyui_support_tools.shared.semantic_erase.query_resolver import resolve_target


# {
# 責務: [ReviewRequiredError: 自動消去に十分なregion evidenceが無いことを示す]
# フィールド: [review_candidates: user review可能なmask候補]
# }
class ReviewRequiredError(RuntimeError):
    # {
    # 責務: [__init__: review-only candidateを保持してerrorを作る]
    # 処理: [1: candidate tupleを保持する, 2: failure reasonを設定する]
    # 引数: [message: reason, review_candidates: candidate tuple]
    # 戻り値: []
    # }
    def __init__(self, message: str, review_candidates: tuple[RegionCandidate, ...] = ()):
        super().__init__(message)
        self.review_candidates = review_candidates


# {
# 責務: [_EvaluatedCandidate: image/mask/backend/evaluationを一括してrankingする]
# フィールド: [candidate,mask,backend,result,evaluation]
# }
@dataclass(frozen=True)
class _EvaluatedCandidate:
    region: RegionCandidate
    mask: object
    result: InpaintResult
    evaluation: object


# {
# 責務: [SemanticEraseService: region proposalからreviewable artifactまでを実行する]
# フィールド: [region_providers,inpaint_backends,retry_limit]
# 処理: [1: sourceを検証する, 2: region候補を選ぶ, 3: fill候補を評価する, 4: non-destructive historyを保存する]
# }
class SemanticEraseService:
    # {
    # 責務: [__init__: injectable detector/backendとlocal baselineを保持する]
    # 処理: [1: region providersを保持する, 2: inpaint backendを初期化する]
    # 引数: [region_providers: query grounding providers, inpaint_backends: mask-fill implementations, retry_limit: local retry budget]
    # 戻り値: []
    # エラー: [ValueError: retry budgetが範囲外の場合]
    # }
    def __init__(
        self,
        region_providers: RegionProviderRegistry | None = None,
        inpaint_backends: InpaintBackendRegistry | None = None,
        retry_limit: int = 2,
    ):
        if not 0 <= retry_limit <= 8:
            raise ValueError("retry limit must be between 0 and 8")
        self.region_providers = region_providers or RegionProviderRegistry()
        self.inpaint_backends = inpaint_backends or create_default_backend_registry()
        self.retry_limit = retry_limit

    # {
    # 責務: [process: Semantic Erase requestを安全に実行する]
    # 処理: [1: imageを安全にdecodeする, 2: semantic/manual maskを提案する, 3: multi-mask/backend候補を評価する, 4: history artifactを保存する]
    # 引数: [request: input and semantic erase specification]
    # 戻り値: [result: selected output, evidence scores, review state]
    # エラー: [ReviewRequiredError: region detectorが候補を返さない場合]
    # }
    def process(self, request: EraseRequest) -> EraseResult:
        source_path = Path(request.image_path).expanduser().absolute()
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("source image must be a regular non-symbolic-link file")
        try:
            with Image.open(source_path) as opened:
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("source image exceeds the 50 megapixel safety limit")
                opened.verify()
            with Image.open(source_path) as opened:
                source = opened.convert("RGB")
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError("source image could not be safely decoded") from exc

        resolved_target = resolve_target(request.target)
        request = replace(request, target=resolved_target)
        regions = resolve_region_candidates(source, request.target, self.region_providers)
        if not regions:
            raise ReviewRequiredError(
                "No target region was found. Register a grounding provider or correct a manual mask."
            )
        selected, review_required = select_matches(regions, request.target)
        if not selected:
            raise ReviewRequiredError("match policy selected no regions", regions)
        replay_mask = _merge_regions(selected).mask
        if request.mode is EraseMode.REVIEW_UNCERTAIN:
            review_required = True

        evaluated = self._evaluate_candidates(source, selected, request)
        if not evaluated:
            raise ReviewRequiredError(
                "all inpaint backends failed to produce a valid candidate", selected
            )
        ranked = sorted(evaluated, key=_candidate_rank, reverse=True)
        best = ranked[0]
        root = (
            Path(request.history_root).expanduser()
            if request.history_root
            else source_path.parent / ".semantic-erase-history"
        )
        history = EraseHistoryStore(root)
        entry = history.record(
            source_path,
            request.target,
            best.result.image,
            best.mask,
            best.result.backend_id,
            accepted=best.evaluation.accepted,
            replay_mask=replay_mask,
            quality_profile=request.quality_profile.value,
        )
        if request.mode is EraseMode.CONFIDENT_AUTO and not best.evaluation.accepted:
            review_required = True
        evaluations = tuple(item.evaluation for item in ranked)
        return EraseResult(
            operation_id=entry.operation_id,
            source_path=str(source_path),
            output_path=str(history.root / entry.output_name),
            selected_mask=best.mask,
            candidate_evaluations=evaluations,
            review_required=review_required,
            residual_checked=best.evaluation.residual_score is not None,
            backend_id=best.result.backend_id,
            backend_warnings=best.result.warnings,
        )

    # {
    # 責務: [replay: saved erase operationを同一source hash上で再実行する]
    # 処理: [1: operation recordを読む, 2: source hash一致を確認する, 3: 保存済mask/policyでpipelineを再実行する]
    # 引数: [source_path: original source, history_root: local operation history, operation_id: replayed operation, quality_profile: execution budget]
    # 戻り値: [result: new non-destructive replay candidate]
    # エラー: [ValueError: source assetが履歴作成後に変わった場合]
    # }
    def replay(
        self,
        source_path: str | Path,
        history_root: str | Path,
        operation_id: str,
        quality_profile: QualityProfile | None = None,
    ) -> EraseResult:
        history = EraseHistoryStore(history_root)
        entry = history.get_entry(operation_id)
        source = Path(source_path).expanduser().absolute()
        if source_sha256(source) != entry.source_sha256:
            raise ValueError("source image changed since the recorded operation")
        target = SemanticEraseTarget(
            query=entry.query,
            normalized_tag=entry.normalized_tag,
            provider_query=entry.provider_query,
            range_label=entry.range_label,
            target_type=EraseTargetType(entry.target_type),
            mask=entry.replay_mask or entry.mask,
            match_policy=MatchPolicy.REMOVE_ALL,
            fill_policy=entry.fill_policy,
            fill_instruction=entry.fill_instruction,
            preserve_rules=entry.preserve_rules,
            confidence_threshold=entry.confidence_threshold,
        )
        return self.process(
            EraseRequest(
                str(source),
                target,
                quality_profile=QualityProfile(quality_profile or entry.quality_profile),
                mode=EraseMode.REVIEW_UNCERTAIN,
                history_root=str(history.root),
            )
        )

    # {
    # 責務: [_evaluate_candidates: mask variantsとbackend routesを試しretry結果を集約する]
    # 処理: [1: mask/backend combinationsを作る, 2: candidateを生成する, 3:評価とresidual retryを行う]
    # 引数: [source: decoded RGB image, regions: selected semantic candidates, request: processing policy]
    # 戻り値: [evaluated: ranked candidate inputs]
    # }
    def _evaluate_candidates(
        self,
        source: Image.Image,
        regions: tuple[RegionCandidate, ...],
        request: EraseRequest,
    ) -> tuple[_EvaluatedCandidate, ...]:
        maximum = request.candidate_limit
        variants = []
        merged = _merge_regions(regions)
        variants.extend(mask_variants(merged.mask, request.quality_profile, max_variants=maximum))
        variants = _unique_masks(variants)[:maximum]
        backends = self.inpaint_backends.route(request.quality_profile)
        if not backends:
            raise RuntimeError("no inpaint backend is registered")
        evaluated = []
        for mask in variants:
            for _, backend in backends:
                if len(evaluated) >= maximum:
                    break
                try:
                    result = backend.inpaint(source, mask, request.target)
                    evaluation = evaluate_candidate(
                        source,
                        result.image,
                        mask,
                        request.target,
                        self.region_providers,
                        preservation_mask=merged.mask,
                    )
                except (ValueError, RuntimeError, OSError):
                    continue
                evaluated.append(_EvaluatedCandidate(merged, mask, result, evaluation))
                if (
                    evaluation.residual_score is not None
                    and evaluation.residual_score >= request.target.confidence_threshold
                ):
                    for retry_mask in make_retry_masks(mask, self.retry_limit):
                        if len(evaluated) >= maximum:
                            break
                        try:
                            retry = backend.inpaint(source, retry_mask, request.target)
                            retry_evaluation = evaluate_candidate(
                                source,
                                retry.image,
                                retry_mask,
                                request.target,
                                self.region_providers,
                                preservation_mask=merged.mask,
                            )
                        except (ValueError, RuntimeError, OSError):
                            continue
                        evaluated.append(
                            _EvaluatedCandidate(merged, retry_mask, retry, retry_evaluation)
                        )
        return tuple(evaluated)


# {
# 責務: [select_matches: user match policyに従ってregion候補を選択する]
# 処理: [1: selected ID条件を検証する, 2: policy別に候補を返す, 3: manual review状態を判定する]
# 引数: [candidates: detected region list, target: selection rules]
# 戻り値: [selection: selected candidates, review_required: user preview needed]
# エラー: [ValueError: required selected matchが無い場合]
# }
def select_matches(
    candidates: tuple[RegionCandidate, ...], target: SemanticEraseTarget
) -> tuple[tuple[RegionCandidate, ...], bool]:
    if (
        target.match_policy is MatchPolicy.REMOVE_ALL
        or target.match_policy is MatchPolicy.INSIDE_RANGE
    ):
        return candidates, False
    if target.match_policy in {MatchPolicy.SELECTED, MatchPolicy.ALL_EXCEPT_SELECTED}:
        if not target.selected_match_id:
            raise ValueError("selected match policy requires selected_match_id")
        selected = tuple(item for item in candidates if item.match_id == target.selected_match_id)
        if len(selected) != 1:
            raise ValueError("selected match ID does not identify exactly one region")
        if target.match_policy is MatchPolicy.SELECTED:
            return selected, False
        return tuple(
            item for item in candidates if item.match_id != target.selected_match_id
        ), False
    return candidates, True


# {
# 責務: [_candidate_rank: residual/preservation/boundary scoresからcandidate順位を計算する]
# 処理: [1: hard reject reasonを優先する, 2: preservation/boundary/residual scoreを組み合わせる]
# 引数: [candidate: evaluated output candidate]
# 戻り値: [rank: sortable scalar score]
# }
def _candidate_rank(candidate: _EvaluatedCandidate) -> float:
    report = candidate.evaluation
    residual = report.residual_score
    if residual is None:
        residual_penalty = 1.0
    else:
        residual_penalty = residual
    return (
        2.0 * float(report.accepted)
        + report.preservation_score
        + report.boundary_score
        - 2.0 * residual_penalty
    )


# {
# 責務: [_unique_masks: 重複するRLE mask候補を順序維持で除去する]
# 処理: [1: first occurrenceを保持する, 2: unique tupleを返す]
# 引数: [masks: proposed mask sequence]
# 戻り値: [unique: mask candidates]
# }
def _unique_masks(masks):
    seen = set()
    result = []
    for mask in masks:
        if mask not in seen:
            seen.add(mask)
            result.append(mask)
    return tuple(result)


# {
# 責務: [_merge_regions: remove-all match policyのselected maskを一つのunionへまとめる]
# 処理: [1: mask dimensionsを一致確認する, 2: binary OR unionを作る, 3: confidence/evidenceを集約する]
# 引数: [regions: selected match regions]
# 戻り値: [merged: union mask region]
# エラー: [ValueError: selected regionsのshapeが一致しない場合]
# }
def _merge_regions(regions: tuple[RegionCandidate, ...]) -> RegionCandidate:
    if not regions:
        raise ValueError("at least one selected region is required")
    shape = (regions[0].mask.height, regions[0].mask.width)
    combined = np.zeros(shape, dtype=bool)
    for region in regions:
        rows = (
            np.frombuffer(region.mask.to_binary_bytes(), dtype=np.uint8)
            .reshape(region.mask.height, region.mask.width)
            .astype(bool)
        )
        if rows.shape != shape:
            raise ValueError("selected region masks must have matching dimensions")
        np.logical_or(combined, rows, out=combined)
    return RegionCandidate(
        mask=type(regions[0].mask).from_binary_bytes(
            regions[0].mask.width, regions[0].mask.height, combined.astype(np.uint8).tobytes()
        ),
        confidence=min(item.confidence for item in regions),
        provider="merged-selection",
        match_id="-".join(item.match_id for item in regions),
        evidence=tuple(value for item in regions for value in item.evidence),
    )


# {
# 責務: [process_batch: folder内のselected imageへ同一semantic erase requestを適用する]
# 処理: [1: pathをstable orderへ並べる, 2: 各画像を個別処理する, 3: review/failed queueを返す]
# 引数: [service: erase service, image_paths: selected input images, template: shared request]
# 戻り値: [items: per-image results]
# }
def process_batch(
    service: SemanticEraseService,
    image_paths: tuple[str | Path, ...],
    template: EraseRequest,
) -> tuple[EraseBatchItem, ...]:
    items = []
    for image_path in sorted(
        (Path(path) for path in image_paths), key=lambda path: str(path).casefold()
    ):
        try:
            result = service.process(replace(template, image_path=str(image_path)))
            status = BatchStatus.REVIEW if result.review_required else BatchStatus.DONE
            items.append(EraseBatchItem(str(image_path), status, result.output_path))
        except ReviewRequiredError as exc:
            items.append(EraseBatchItem(str(image_path), BatchStatus.REVIEW, message=str(exc)))
        except Exception as exc:
            items.append(EraseBatchItem(str(image_path), BatchStatus.FAILED, message=str(exc)))
    return tuple(items)
