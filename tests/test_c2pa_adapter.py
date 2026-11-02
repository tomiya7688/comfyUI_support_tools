import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from comfyui_support_tools.shared.c2pa_adapter import (
    C2paAdapter,
    C2paVerificationError,
    C2paVerificationReport,
)
from comfyui_support_tools.shared.transparency_contracts import (
    MediaClassification,
    ModelDisclosure,
    ProvenanceAction,
    ProvenanceRecord,
    TransparencySettings,
    resolve_transparency_enabled,
)


# {
# 責務: [ _Reader: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class _Reader:
    manifest = None
    results = None
    state = None

    # {
    # 責務: [ __init__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, *_args, **_kwargs]
    # 戻り値: [処理結果]
    # }
    def __init__(self, *_args, **_kwargs):
        pass

    # {
    # 責務: [ __enter__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def __enter__(self):
        return self

    # {
    # 責務: [ __exit__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self, *_args]
    # 戻り値: [処理結果]
    # }
    def __exit__(self, *_args):
        return False

    # {
    # 責務: [ is_embedded: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def is_embedded(self):
        return self.manifest is not None

    # {
    # 責務: [ json: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def json(self):
        import json

        return json.dumps(self.manifest)

    # {
    # 責務: [ get_validation_state: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def get_validation_state(self):
        return self.state

    # {
    # 責務: [ get_validation_results: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def get_validation_results(self):
        return self.results


# {
# 責務: [ C2paAdapterTests: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class C2paAdapterTests(unittest.TestCase):
    # {
    # 責務: [ _sdk: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [なし]
    # 戻り値: [処理結果]
    # }
    @staticmethod
    def _sdk():
        manifest_not_found = type("ManifestNotFound", (Exception,), {})
        return SimpleNamespace(
            Reader=_Reader,
            C2paError=SimpleNamespace(ManifestNotFound=manifest_not_found),
        )

    # {
    # 責務: [ test_c2pa_export_requires_explicit_opt_in: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_c2pa_export_requires_explicit_opt_in(self):
        adapter = C2paAdapter()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            source.write_bytes(b"not inspected")
            with self.assertRaisesRegex(ValueError, "explicit Transparency Assist"):
                adapter.sign(
                    source,
                    Path(directory) / "output.png",
                    ProvenanceRecord(classification=MediaClassification.GENERATED),
                    object(),
                    TransparencySettings(),
                )

    # {
    # 責務: [ test_verification_distinguishes_signature_from_trust: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_verification_distinguishes_signature_from_trust(self):
        active = {
            "assertions": [
                {
                    "label": "c2pa.actions.v2",
                    "data": {
                        "actions": [
                            {
                                "action": "c2pa.created",
                                "digitalSourceType": (
                                    "http://cv.iptc.org/newscodes/digitalsourcetype/"
                                    "trainedAlgorithmicMedia"
                                ),
                            }
                        ]
                    },
                },
                {"label": "c2pa.ai-disclosure", "data": {"modelType": "c2pa.types.model"}},
            ],
            "ingredients": [],
        }
        _Reader.manifest = {"active_manifest": "urn:test", "manifests": {"urn:test": active}}
        _Reader.results = {
            "activeManifest": {
                "success": [{"code": "claimSignature.validated"}],
                "failure": [{"code": "signingCredential.untrusted"}],
            }
        }
        _Reader.state = "Valid"
        sdk = self._sdk()
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "asset.png"
            media.write_bytes(b"placeholder")
            adapter = C2paAdapter()
            with patch.object(adapter, "_sdk", return_value=sdk):
                report = adapter.verify(media, expected_source_type="trainedAlgorithmicMedia")
        self.assertTrue(report.signature_valid)
        self.assertFalse(report.trusted)
        self.assertTrue(report.ai_disclosure_present)
        self.assertFalse(report.verified)

    # {
    # 責務: [ test_verification_requires_expected_iptc_source_type: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_verification_requires_expected_iptc_source_type(self):
        _Reader.manifest = {
            "active_manifest": "urn:test",
            "manifests": {"urn:test": {"assertions": [], "ingredients": []}},
        }
        sdk = self._sdk()
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "asset.png"
            media.write_bytes(b"placeholder")
            adapter = C2paAdapter()
            with patch.object(adapter, "_sdk", return_value=sdk):
                with self.assertRaisesRegex(C2paVerificationError, "expected IPTC source type"):
                    adapter.verify(media, expected_source_type="trainedAlgorithmicMedia")

    # {
    # 責務: [ test_no_manifest_is_not_reported_as_verified: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_no_manifest_is_not_reported_as_verified(self):
        _Reader.manifest = None
        sdk = self._sdk()
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "asset.png"
            media.write_bytes(b"placeholder")
            adapter = C2paAdapter()
            with patch.object(adapter, "_sdk", return_value=sdk):
                report = adapter.verify(media)
        self.assertEqual(
            report,
            C2paVerificationReport(False, None, None, 0, False, False, False, False),
        )

    # {
    # 責務: [ test_verification_rejects_malformed_c2pa_24_ai_disclosure: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_verification_rejects_malformed_c2pa_24_ai_disclosure(self):
        _Reader.manifest = {
            "active_manifest": "urn:test",
            "manifests": {
                "urn:test": {
                    "assertions": [
                        {
                            "label": "c2pa.actions.v2",
                            "data": {
                                "actions": [
                                    {
                                        "action": "c2pa.created",
                                        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                                    }
                                ]
                            },
                        },
                        {"label": "c2pa.ai-disclosure", "data": {"modelType": "invalid.model"}},
                    ],
                    "ingredients": [],
                }
            },
        }
        sdk = self._sdk()
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "asset.png"
            media.write_bytes(b"placeholder")
            adapter = C2paAdapter()
            with patch.object(adapter, "_sdk", return_value=sdk):
                with self.assertRaisesRegex(C2paVerificationError, "C2PA 2.4 schema"):
                    adapter.verify(media)

    # {
    # 責務: [ test_c2pa_24_ai_disclosure_uses_official_labels_and_privacy_levels: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_c2pa_24_ai_disclosure_uses_official_labels_and_privacy_levels(self):
        record = ProvenanceRecord(
            classification=MediaClassification.GENERATED,
            prompt="secret prompt is never part of this assertion",
            model_family="Flux",
            model_id="flux-dev",
            model_version="1.2",
            c2pa_model_type="c2pa.types.model.pytorch",
            actions=(ProvenanceAction("generation", True, user_oversight="prompt_guided"),),
        )
        default = C2paAdapter.ai_disclosure_assertion(record, TransparencySettings(enabled=True))
        self.assertEqual(default["label"], "c2pa.ai-disclosure")
        self.assertEqual(
            default["data"],
            {
                "modelType": "c2pa.types.model.pytorch",
                "contentProfile": {"humanOversightLevel": "prompt_guided"},
            },
        )
        disclosed = C2paAdapter.ai_disclosure_assertion(
            record,
            TransparencySettings(
                enabled=True,
                model_disclosure=ModelDisclosure.MODEL_ID_AND_VERSION,
            ),
        )
        self.assertEqual(disclosed["data"]["modelIdentifier"], "flux-dev")
        self.assertEqual(disclosed["data"]["modelName"], "Flux 1.2")
        self.assertNotIn("secret prompt", str(disclosed))

    # {
    # 責務: [ test_export_override_precedes_application_and_global_then_defaults_off: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_export_override_precedes_application_and_global_then_defaults_off(self):
        self.assertFalse(resolve_transparency_enabled())
        self.assertFalse(resolve_transparency_enabled(True, application_override=False))
        self.assertTrue(resolve_transparency_enabled(False, application_override=True))
        self.assertFalse(
            resolve_transparency_enabled(True, application_override=True, export_override=False)
        )
        self.assertTrue(
            resolve_transparency_enabled(False, application_override=False, export_override=True)
        )


if __name__ == "__main__":
    unittest.main()
