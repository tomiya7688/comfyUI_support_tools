import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from comfyui_support_tools.shared.semantic_erase.backends import (
    CallableInpaintBackend,
    InpaintBackendRegistry,
    OpenCVTeleaBackend,
    edit_mask_stroke,
    mask_variants,
)
from comfyui_support_tools.shared.semantic_erase.contracts import (
    EraseMode,
    EraseRequest,
    FillPolicy,
    MatchPolicy,
    QualityProfile,
    RegionBox,
    RegionCandidate,
    RLEMask,
    SemanticEraseTarget,
)
from comfyui_support_tools.shared.semantic_erase.evaluator import evaluate_candidate
from comfyui_support_tools.shared.semantic_erase.history import EraseHistoryStore
from comfyui_support_tools.shared.semantic_erase.providers import (
    GroundedSegmentationProvider,
    RegionProviderRegistry,
    TextDetection,
    apply_range_constraint,
    resolve_region_candidates,
)
from comfyui_support_tools.shared.semantic_erase.query_resolver import (
    resolve_semantic_query,
    resolve_target,
)
from comfyui_support_tools.shared.semantic_erase.service import (
    ReviewRequiredError,
    SemanticEraseService,
    select_matches,
)


# {
# 責務: [SemanticEraseTests: erase契約・provider・inpaint・historyの受け入れ動作を検証する]
# フィールド: [なし]
# 処理: [1: mask/selection/provider behaviorを確認する, 2: non-destructive pipelineを検証する]
# }
class SemanticEraseTests(unittest.TestCase):
    # {
    # 責務: [test_natural_language_query_separates_target_scope_and_fill_instruction: deterministic query resolver structures instructions]
    # 処理: [1: English/Japanese target phrasesをparseする, 2: normalized tag/scope/fill policyを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_natural_language_query_separates_target_scope_and_fill_instruction(self):
        resolved = resolve_semantic_query(
            "remove only the blood stain from the shirt fill: matching fabric texture"
        )
        self.assertEqual(resolved.normalized_tag, "blood stain")
        self.assertEqual(resolved.range_label, "the shirt")
        self.assertEqual(resolved.fill_instruction, "matching fabric texture")
        target = resolve_target(SemanticEraseTarget("顔のあざを消す"))
        self.assertEqual(target.normalized_tag, "あざ")
        self.assertEqual(target.provider_query, "あざ")

    # {
    # 責務: [test_rle_mask_round_trip_and_invalid_runs: mask RLE round tripと範囲検証を確認する]
    # 処理: [1: sparse binary maskをencode/decodeする, 2: out-of-bounds runを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_rle_mask_round_trip_and_invalid_runs(self):
        rows = [[False, True, True], [True, False, True]]
        mask = RLEMask.from_rows(rows)
        self.assertEqual(mask.to_rows(), tuple(tuple(row) for row in rows))
        self.assertEqual(mask.area, 4)
        with self.assertRaisesRegex(ValueError, "in bounds"):
            RLEMask(2, 2, ((3, 2),))

    # {
    # 責務: [test_region_match_ids_are_stable_and_request_accepts_paths: identifiers and public path contract are deterministic]
    # 処理: [1: identical mask candidatesを作る, 2: stable IDとPath normalizationを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_region_match_ids_are_stable_and_request_accepts_paths(self):
        mask = RLEMask.from_rows([[True, False], [False, True]])
        first = RegionCandidate(mask, 0.9, "fixture")
        second = RegionCandidate(mask, 0.9, "fixture")
        self.assertEqual(first.match_id, second.match_id)
        request = EraseRequest(
            Path("input.png"), SemanticEraseTarget("stain"), quality_profile="fast"
        )
        self.assertEqual(request.image_path, "input.png")
        self.assertIs(request.quality_profile, QualityProfile.FAST)

    # {
    # 責務: [test_target_validation_requires_custom_fill_and_inside_range: match/fill制約を検証する]
    # 処理: [1: custom fill without instructionを拒否する, 2: inside-range without boxを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_target_validation_requires_custom_fill_and_inside_range(self):
        with self.assertRaisesRegex(ValueError, "fill instruction"):
            SemanticEraseTarget("bruise", fill_policy=FillPolicy.CUSTOM)
        with self.assertRaisesRegex(ValueError, "range constraint"):
            SemanticEraseTarget("blood", match_policy=MatchPolicy.INSIDE_RANGE)

    # {
    # 責務: [test_mask_strokes_add_and_subtract_user_corrections: manual mask brushで追加と除去を行う]
    # 処理: [1: brush addを適用する, 2: erase strokeを適用する, 3: area変化を検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_mask_strokes_add_and_subtract_user_corrections(self):
        mask = RLEMask.from_rows([[False] * 16 for _ in range(16)])
        added = edit_mask_stroke(mask, ((0.5, 0.5),), radius=0.2)
        removed = edit_mask_stroke(added, ((0.5, 0.5),), radius=0.05, erase=True)
        self.assertGreater(added.area, removed.area)
        self.assertGreater(removed.area, 0)

    # {
    # 責務: [test_range_constraint_intersects_provider_mask: user range limits region proposals]
    # 処理: [1: full-frame candidateを作る, 2: range boxでmaskを制限する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_range_constraint_intersects_provider_mask(self):
        candidate = RegionCandidate(
            RLEMask.from_rows([[True] * 10 for _ in range(10)]), 0.9, "test"
        )
        constrained = apply_range_constraint(candidate, RegionBox(0.2, 0.2, 0.4, 0.4))
        self.assertEqual(constrained.mask.area, 16)
        self.assertEqual(constrained.evidence[-1], "range-constrained")

    # {
    # 責務: [test_match_policy_supports_selected_all_except_and_review: selection rules return expected candidates]
    # 処理: [1: two matchesを作る, 2: selected/all-except/reviewを評価する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_match_policy_supports_selected_all_except_and_review(self):
        candidates = (
            RegionCandidate(RLEMask.from_rows([[True]]), 0.9, "test", match_id="a"),
            RegionCandidate(RLEMask.from_rows([[True]]), 0.8, "test", match_id="b"),
        )
        selected, review = select_matches(
            candidates,
            SemanticEraseTarget(
                "glasses", match_policy=MatchPolicy.SELECTED, selected_match_id="b"
            ),
        )
        self.assertEqual([item.match_id for item in selected], ["b"])
        self.assertFalse(review)
        remaining, _ = select_matches(
            candidates,
            SemanticEraseTarget(
                "glasses", match_policy=MatchPolicy.ALL_EXCEPT_SELECTED, selected_match_id="a"
            ),
        )
        self.assertEqual([item.match_id for item in remaining], ["b"])
        all_matches, review = select_matches(candidates, SemanticEraseTarget("glasses"))
        self.assertEqual(len(all_matches), 2)
        self.assertTrue(review)

    # {
    # 責務: [test_grounded_provider_segments_text_detections: detector boxes are converted into masks]
    # 処理: [1: fake grounding/segmentation adaptersを注入する, 2: query candidateを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_grounded_provider_segments_text_detections(self):
        # {
        # 責務: [Detector: fake text grounding detector protocolを実装する]
        # フィールド: [なし]
        # }
        class Detector:
            # {
            # 責務: [detect: fixture queryに対応するbox candidateを返す]
            # 処理: [1: fixed confidence付きboxを返す]
            # 引数: [self, _image, query]
            # 戻り値: [detections]
            # }
            def detect(self, _image, query):
                return [TextDetection(RegionBox(0.25, 0.25, 0.5, 0.5), 0.95, query)]

        # {
        # 責務: [Segmenter: mask fixture segmentation adapterを実装する]
        # フィールド: [なし]
        # }
        class Segmenter:
            # {
            # 責務: [segment: fixture boxへsmall binary regionを返す]
            # 処理: [1: HxW empty maskを作る, 2: target squareをsetする]
            # 引数: [self, image, _box]
            # 戻り値: [mask]
            # }
            def segment(self, image, _box):
                mask = np.zeros((image.height, image.width), dtype=bool)
                mask[2:6, 2:6] = True
                return mask

        image = Image.new("RGB", (8, 8), "white")
        provider = GroundedSegmentationProvider(Detector(), Segmenter())
        candidates = provider.propose(image, SemanticEraseTarget("remove the bag"))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].mask.area, 16)

    # {
    # 責務: [test_provider_registry_collects_range_constrained_candidates: registry yields only in-range candidates]
    # 処理: [1: fake providerをregisterする, 2: range付きqueryを解決する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_provider_registry_collects_range_constrained_candidates(self):
        # {
        # 責務: [Provider: full image maskを返すfake region provider]
        # フィールド: [なし]
        # }
        class Provider:
            # {
            # 責務: [propose: fixture image sizeのfull-image candidateを返す]
            # 処理: [1: image-sized RLE maskを返す]
            # 引数: [self, image, _target]
            # 戻り値: [candidate]
            # }
            def propose(self, image, _target):
                return (
                    RegionCandidate(
                        RLEMask.from_rows([[True] * image.width for _ in range(image.height)]),
                        0.9,
                        "wrong-id",
                    ),
                )

        registry = RegionProviderRegistry()
        registry.register("fixture-grounding", Provider())
        target = SemanticEraseTarget("stain", range_constraint=RegionBox(0.25, 0.25, 0.5, 0.5))
        resolved = resolve_region_candidates(Image.new("RGB", (8, 8)), target, registry)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].provider, "fixture-grounding")
        self.assertEqual(resolved[0].mask.area, 16)

    # {
    # 責務: [test_mask_variants_expand_small_targets_by_quality_budget: quality profile controls dilation candidates]
    # 処理: [1: single pixel targetを作る, 2: fast/quality mask variantsを比較する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_mask_variants_expand_small_targets_by_quality_budget(self):
        mask = RLEMask.from_rows([[False] * 12 for _ in range(12)])
        rows = [list(row) for row in mask.to_rows()]
        rows[5][5] = True
        mask = RLEMask.from_rows(rows)
        fast = mask_variants(mask, QualityProfile.FAST)
        quality = mask_variants(mask, QualityProfile.QUALITY)
        self.assertEqual(len(fast), 1)
        self.assertGreater(max(item.area for item in quality), mask.area)

    # {
    # 責務: [test_telea_inpaint_changes_only_masked_pixels: CPU fallback preserves every outside pixel]
    # 処理: [1: source rectangleとmaskを作る, 2: Telea inpaintを行う, 3: outside exact equalityを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_telea_inpaint_changes_only_masked_pixels(self):
        source = np.full((24, 24, 3), 120, dtype=np.uint8)
        source[8:16, 8:16] = 0
        image = Image.fromarray(source)
        rows = [[False] * 24 for _ in range(24)]
        for y in range(8, 16):
            for x in range(8, 16):
                rows[y][x] = True
        mask = RLEMask.from_rows(rows)
        result = OpenCVTeleaBackend().inpaint(image, mask, SemanticEraseTarget("artifact"))
        output = np.asarray(result.image)
        self.assertTrue(np.array_equal(output[~np.asarray(rows)], source[~np.asarray(rows)]))
        self.assertGreater(int(output[10, 10].mean()), 0)

    # {
    # 責務: [test_expanded_mask_dilation_does_not_hide_non_target_drift: preservation score uses original target region]
    # 処理: [1: target and expanded masksを作る, 2: expansion-only pixelsのdriftを評価する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_expanded_mask_dilation_does_not_hide_non_target_drift(self):
        source = Image.new("RGB", (8, 8), "white")
        output = np.asarray(source).copy()
        output[2:5, 2:5] = (0, 0, 0)
        base_rows = [[False] * 8 for _ in range(8)]
        base_rows[3][3] = True
        expanded_rows = [[False] * 8 for _ in range(8)]
        for y in range(2, 5):
            for x in range(2, 5):
                expanded_rows[y][x] = True
        report = evaluate_candidate(
            source,
            Image.fromarray(output),
            RLEMask.from_rows(expanded_rows),
            SemanticEraseTarget("artifact"),
            RegionProviderRegistry(),
            preservation_mask=RLEMask.from_rows(base_rows),
        )
        self.assertLess(report.preservation_score, 0.995)

    # {
    # 責務: [test_service_saves_review_candidate_without_touching_source: pipeline preserves source and records preview]
    # 処理: [1: PNGとmanual maskを作る, 2: reviewable serviceを実行する, 3: output/history/undoを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_service_saves_review_candidate_without_touching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            source = np.full((32, 32, 3), 140, dtype=np.uint8)
            source[12:20, 12:20] = 0
            Image.fromarray(source).save(source_path)
            source_bytes = source_path.read_bytes()
            rows = [[False] * 32 for _ in range(32)]
            for y in range(12, 20):
                for x in range(12, 20):
                    rows[y][x] = True
            target = SemanticEraseTarget("unwanted square", mask=RLEMask.from_rows(rows))
            request = EraseRequest(
                str(source_path),
                target,
                quality_profile=QualityProfile.FAST,
                history_root=str(root / "history"),
            )
            result = SemanticEraseService().process(request)
            self.assertTrue(result.review_required)
            self.assertFalse(result.residual_checked)
            self.assertTrue(Path(result.output_path).is_file())
            self.assertEqual(source_path.read_bytes(), source_bytes)
            store = EraseHistoryStore(root / "history")
            self.assertIsNone(store.undo())
            self.assertEqual(store.redo(), Path(result.output_path))

    # {
    # 責務: [test_history_branches_preserve_candidates_when_editing_after_undo: branch-aware undo/redo keeps earlier candidates]
    # 処理: [1: main branchへ2件保存する, 2: undo後に新candidateを保存する, 3: old/new branch outputを切替確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_history_branches_preserve_candidates_when_editing_after_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            mask = RLEMask.from_rows([[True] * 8 for _ in range(8)])
            target = SemanticEraseTarget("remove region", mask=mask)
            service = SemanticEraseService()
            request = EraseRequest(
                str(source_path),
                target,
                quality_profile=QualityProfile.FAST,
                history_root=str(root / "history"),
            )
            first = service.process(request)
            second = service.process(request)
            store = EraseHistoryStore(root / "history")
            self.assertEqual(store.undo(), Path(first.output_path))
            third = service.process(request)
            branches = store.branch_ids()
            self.assertEqual(len(branches), 2)
            self.assertEqual(store.active_output(), Path(third.output_path))
            self.assertEqual(store.switch_branch("main"), Path(second.output_path))

    # {
    # 責務: [test_history_replay_requires_matching_source_and_recreates_candidate: saved mask/policy can be rerun safely]
    # 処理: [1: operationを保存する, 2: hash一致sourceでreplayする, 3: changed sourceを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_history_replay_requires_matching_source_and_recreates_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            Image.new("RGB", (12, 12), "white").save(source_path)
            rows = [[False] * 12 for _ in range(12)]
            rows[4:8] = [row[:4] + [True] * 4 + row[8:] for row in rows[4:8]]
            target = SemanticEraseTarget("remove sample mark", mask=RLEMask.from_rows(rows))
            request = EraseRequest(
                str(source_path),
                target,
                quality_profile=QualityProfile.FAST,
                history_root=str(root / "history"),
            )
            service = SemanticEraseService()
            initial = service.process(request)
            replayed = service.replay(
                source_path, root / "history", initial.operation_id, QualityProfile.FAST
            )
            self.assertNotEqual(initial.operation_id, replayed.operation_id)
            source_path.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "source image changed"):
                service.replay(source_path, root / "history", initial.operation_id)

    # {
    # 責務: [test_provider_backed_auto_erase_rechecks_target_and_accepts_local_fill: semantic plugin completes guarded auto mode]
    # 処理: [1: color-evidence test providerを登録する, 2: target queryとlocal fillを実行する, 3: residual/preservation/originalを検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_provider_backed_auto_erase_rechecks_target_and_accepts_local_fill(self):
        # {
        # 責務: [RedMarkProvider: red pixel evidenceをtarget regionへ変換するfixture provider]
        # フィールド: [なし]
        # }
        class RedMarkProvider:
            # {
            # 責務: [propose: red mark maskがあればconfidence付きcandidateを返す]
            # 処理: [1: RGB evidenceを抽出する, 2: mask有無を判定してcandidateを作る]
            # 引数: [self, image, _target]
            # 戻り値: [candidate tuple]
            # }
            def propose(self, image, _target):
                pixels = np.asarray(image.convert("RGB"))
                mask = (pixels[:, :, 0] > 200) & (pixels[:, :, 1] < 50)
                if not mask.any():
                    return ()
                return (
                    RegionCandidate(
                        RLEMask.from_rows(mask.tolist()),
                        0.99,
                        "fixture-red-mark",
                        evidence=("red mark",),
                    ),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "red-mark.png"
            pixels = np.full((32, 32, 3), (40, 80, 180), dtype=np.uint8)
            pixels[12:20, 12:20] = (240, 10, 10)
            Image.fromarray(pixels).save(source_path)
            original = source_path.read_bytes()
            providers = RegionProviderRegistry()
            providers.register("fixture-red-mark", RedMarkProvider())
            target = SemanticEraseTarget("remove red mark", match_policy=MatchPolicy.REMOVE_ALL)
            request = EraseRequest(
                str(source_path),
                target,
                quality_profile=QualityProfile.FAST,
                mode=EraseMode.CONFIDENT_AUTO,
                history_root=str(root / "history"),
            )
            result = SemanticEraseService(region_providers=providers).process(request)
            self.assertFalse(result.review_required)
            self.assertTrue(result.residual_checked)
            self.assertEqual(result.candidate_evaluations[0].residual_score, 0.0)
            self.assertEqual(source_path.read_bytes(), original)

    # {
    # 責務: [test_semantic_query_without_provider_fails_closed: model-free tag-only inference is not fabricated]
    # 処理: [1: source imageを作る, 2: no-provider requestを実行する, 3: review-safe errorを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_semantic_query_without_provider_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "image.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            request = EraseRequest(str(source_path), SemanticEraseTarget("bruise on left cheek"))
            with self.assertRaisesRegex(ReviewRequiredError, "No target region"):
                SemanticEraseService().process(request)

    # {
    # 責務: [test_backend_registry_prioritizes_cpu_fallback_and_callable_models: plugin backends stay replaceable]
    # 処理: [1: injected backendを登録する, 2: quality/fast routing orderを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_backend_registry_prioritizes_cpu_fallback_and_callable_models(self):
        registry = InpaintBackendRegistry()
        registry.register(
            "z-model", CallableInpaintBackend("z-model", lambda image, _mask, _target: image)
        )
        registry.register("opencv-telea", OpenCVTeleaBackend())
        self.assertEqual(registry.route(QualityProfile.FAST)[0][0], "opencv-telea")
        self.assertEqual(len(registry.route(QualityProfile.QUALITY)), 2)


if __name__ == "__main__":
    unittest.main()
