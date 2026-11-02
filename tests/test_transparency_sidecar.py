import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.transparency_contracts import (
    MediaClassification,
    ModelDisclosure,
    PromptDisclosure,
    ProvenanceAction,
    ProvenanceRecord,
    TransparencySettings,
    WorkflowDisclosure,
    resolve_profile,
)
from comfyui_support_tools.shared.transparency_sidecar import build_transparency_sidecar


# {
# 責務: [ TransparencySidecarTests: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class TransparencySidecarTests(unittest.TestCase):
    # {
    # 責務: [ setUp: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def setUp(self):
        self.record = ProvenanceRecord(
            classification=MediaClassification.GENERATED,
            prompt="private production note and prompt",
            sanitized_prompt_summary="landscape illustration",
            model_family="Flux",
            model_id="flux-dev",
            model_version="1.2",
            model_hash="ab" * 32,
            workflow_id="workflow-7",
            workflow_json={"6": {"class_type": "CheckpointLoaderSimple"}},
            actions=(ProvenanceAction(operation="generation", ai_involvement=True),),
        )

    # {
    # 責務: [ test_defaults_disable_assist_and_disclosure_levels: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_defaults_disable_assist_and_disclosure_levels(self):
        settings = TransparencySettings()
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.prompt_disclosure, PromptDisclosure.NONE)
        self.assertEqual(settings.model_disclosure, ModelDisclosure.NONE)
        self.assertEqual(settings.workflow_disclosure, WorkflowDisclosure.NONE)
        self.assertFalse(settings.sign_c2pa)
        with self.assertRaisesRegex(ValueError, "disabled"):
            build_transparency_sidecar(self.record, settings, output_sha256="a" * 64)

    # {
    # 責務: [ test_minimum_disclosure_never_writes_prompt_model_or_workflow: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_minimum_disclosure_never_writes_prompt_model_or_workflow(self):
        payload = build_transparency_sidecar(
            self.record, TransparencySettings(enabled=True), output_sha256="a" * 64
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("private production note", encoded)
        self.assertNotIn("flux-dev", encoded)
        self.assertNotIn("CheckpointLoaderSimple", encoded)
        self.assertEqual(payload["generated_or_modified"], "generated")
        self.assertEqual(payload["legal_profile"]["version"], "2026.1")
        self.assertIn("does not determine legal obligations", payload["notice"])

    # {
    # 責務: [ test_hash_and_summary_disclosure_are_explicit_and_stable: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_hash_and_summary_disclosure_are_explicit_and_stable(self):
        payload = build_transparency_sidecar(
            self.record,
            TransparencySettings(
                enabled=True,
                prompt_disclosure=PromptDisclosure.HASH_ONLY,
                model_disclosure=ModelDisclosure.FAMILY,
                workflow_disclosure=WorkflowDisclosure.HASH,
            ),
            output_sha256="b" * 64,
        )
        disclosure = payload["disclosure"]
        self.assertEqual(
            disclosure["prompt"]["sha256"],
            hashlib.sha256(self.record.prompt.encode()).hexdigest(),
        )
        self.assertEqual(disclosure["model"]["family"], "Flux")
        self.assertEqual(
            disclosure["workflow"]["sha256"],
            hashlib.sha256(b'{"6":{"class_type":"CheckpointLoaderSimple"}}').hexdigest(),
        )

    # {
    # 責務: [ test_full_and_sanitized_disclosure_require_explicit_levels: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_full_and_sanitized_disclosure_require_explicit_levels(self):
        summary = build_transparency_sidecar(
            self.record,
            TransparencySettings(
                enabled=True,
                prompt_disclosure=PromptDisclosure.SANITIZED_SUMMARY,
                model_disclosure=ModelDisclosure.MODEL_ID_AND_VERSION,
                workflow_disclosure=WorkflowDisclosure.ID,
            ),
            output_sha256="c" * 64,
        )
        self.assertEqual(summary["disclosure"]["prompt"]["summary"], "landscape illustration")
        self.assertNotIn("private production note", json.dumps(summary))
        self.assertEqual(summary["disclosure"]["model"]["id"], "flux-dev")
        self.assertEqual(summary["disclosure"]["workflow"]["id"], "workflow-7")

        full = build_transparency_sidecar(
            self.record,
            TransparencySettings(
                enabled=True,
                prompt_disclosure=PromptDisclosure.FULL,
                workflow_disclosure=WorkflowDisclosure.FULL,
            ),
            output_sha256="d" * 64,
        )
        self.assertEqual(full["disclosure"]["prompt"]["text"], self.record.prompt)
        self.assertEqual(full["disclosure"]["workflow"]["data"], self.record.workflow_json)

    # {
    # 責務: [ test_source_assets_are_hashed_without_path_disclosure: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_source_assets_are_hashed_without_path_disclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private-name.png"
            source.write_bytes(b"source bytes")
            payload = build_transparency_sidecar(
                ProvenanceRecord(source_assets=(str(source),)),
                TransparencySettings(enabled=True),
                output_sha256="e" * 64,
            )
            self.assertEqual(
                payload["source_assets"][0]["sha256"], hashlib.sha256(b"source bytes").hexdigest()
            )
            self.assertNotIn(str(source), json.dumps(payload))

    # {
    # 責務: [ test_unknown_profile_and_unsupported_media_fail_closed: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_unknown_profile_and_unsupported_media_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown transparency profile"):
            resolve_profile("future-profile")
        with self.assertRaisesRegex(ValueError, "does not support"):
            build_transparency_sidecar(
                ProvenanceRecord(content_type="model3d"),
                TransparencySettings(enabled=True),
                output_sha256="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
