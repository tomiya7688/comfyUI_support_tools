import unittest

from src.comfyui_support_tools.shared.model_family_registry import (
    ModelFamilyDetectorRegistry,
    ModelFamilyEvidence,
)
from src.comfyui_support_tools.shared.model_identity import (
    ModelFamily,
    ModelFamilyId,
    ModelKind,
    classify_model,
)


# {
# 責務: [ ModelFamilyRegistryTests: detector extensionとconflict resolutionを検証する ]
# フィールド: []
# 処理: [ 1: fixture detectorを登録する, 2: applicability/provenance/conflictを確認する ]
# }
class ModelFamilyRegistryTests(unittest.TestCase):
    # {
    # 責務: [ _FixtureDetector: 固定fixture evidenceを返すextension provider ]
    # フィールド: [ family: family ID, applicable_kinds: detector対象kind ]
    # 処理: []
    # }
    class _FixtureDetector:
        detector_id = "fixture.custom_family"
        version = "test-v1"
        applicable_kinds = frozenset({"checkpoint"})

        # {
        # 責務: [ __init__: detector fixtureのfamilyを設定する ]
        # 処理: [ 1: familyを保存する ]
        # 引数: [ self: detector, family: fixture family ]
        # 戻り値: []
        # }
        def __init__(self, family):
            self.family = family

        # {
        # 責務: [ detect: filenameやtensorを使わずfixture evidenceを返す ]
        # 処理: [ 1: positive fixtureではfamily evidenceを返す, 2: その他では空を返す ]
        # 引数: [ self: detector, model_path: path, metadata: metadata, tensor_shapes: shapes ]
        # 戻り値: [ evidence: 検出結果 ]
        # }
        def detect(self, model_path, metadata, tensor_shapes):
            if model_path.endswith("positive.model"):
                return (
                    ModelFamilyEvidence(
                        self.family,
                        "fixture structural evidence",
                        0.75,
                        self.detector_id,
                        self.version,
                    ),
                )
            return ()

    # {
    # 責務: [ test_new_family_registers_without_core_detector_changes: extension登録だけで新familyを識別する ]
    # 処理: [ 1: custom detectorを登録する, 2: family/confidence/provenanceを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_new_family_registers_without_core_detector_changes(self):
        registry = ModelFamilyDetectorRegistry()
        registry.register(self._FixtureDetector("new_architecture"))
        result = classify_model("positive.model", detector_registry=registry)
        self.assertEqual(result.family, ModelFamilyId("new_architecture"))
        self.assertEqual(result.confidence, 0.75)
        self.assertEqual(result.detector_provenance, ("fixture.custom_family@test-v1",))

    # {
    # 責務: [ test_conflicting_path_and_detector_evidence_becomes_unknown: filename conflictをunknownにする ]
    # 処理: [ 1: positive fixtureをSDXL pathで分類する, 2: unknownを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_conflicting_path_and_detector_evidence_becomes_unknown(self):
        registry = ModelFamilyDetectorRegistry()
        registry.register(self._FixtureDetector("custom"))
        result = classify_model("models/sdxl/positive.model", detector_registry=registry)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertEqual(result.confidence, 0.0)

    # {
    # 責務: [ test_detector_applicability_limits_model_kind: 対象外kindへdetectorを適用しない ]
    # 処理: [ 1: checkpoint専用detectorでLoRAを分類する, 2: unknownを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_detector_applicability_limits_model_kind(self):
        registry = ModelFamilyDetectorRegistry()
        registry.register(self._FixtureDetector("custom"))
        result = classify_model(
            "positive.model", declared_kind=ModelKind.LORA, detector_registry=registry
        )
        self.assertEqual(result.family, ModelFamily.UNKNOWN)

    # {
    # 責務: [ test_negative_fixture_does_not_match_family: near-match negative fixtureをunknownに保つ ]
    # 処理: [ 1: negative fixtureを分類する, 2: detectorが不一致とすることを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_negative_fixture_does_not_match_family(self):
        registry = ModelFamilyDetectorRegistry()
        registry.register(self._FixtureDetector("custom"))
        result = classify_model("negative-near-match.model", detector_registry=registry)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertIsNone(result.confidence)

    # {
    # 責務: [ test_duplicate_detector_ids_are_rejected: detector IDの衝突を拒否する ]
    # 処理: [ 1: 同じIDを2回登録する, 2: ValueErrorを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_duplicate_detector_ids_are_rejected(self):
        registry = ModelFamilyDetectorRegistry()
        registry.register(self._FixtureDetector("one"))
        with self.assertRaises(ValueError):
            registry.register(self._FixtureDetector("two"))


if __name__ == "__main__":
    unittest.main()
