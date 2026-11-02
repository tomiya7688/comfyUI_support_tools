from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.shared.model_identity import ModelFamily, ModelKind, classify_model
from src.comfyui_support_tools.shared.safetensors_metadata import (
    SafetensorsMetadataError,
    read_safetensors_metadata,
)


# {
#   責務: [ModelIdentityTests: related test fixtures and cases for ModelIdentity behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class ModelIdentityTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_family_can_be_inferred_from_model_path: verifies the behavior described by "family can be inferred from model path",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for family can be inferred from model path,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_family_can_be_inferred_from_model_path(self):
        cases = (
            (r'models\checkpoints\sd15\illustration.safetensors', ModelFamily.SD_1_5),
            (r'models\checkpoints\sdxl\illustration.safetensors', ModelFamily.SDXL),
            (r'models\unet\flux1-dev.safetensors', ModelFamily.FLUX),
            (r'models\checkpoints\anima_baseV10.safetensors', ModelFamily.ANIMA),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(classify_model(path).family, expected)

    # {
    #   責務: [
    #     test_metadata_family_signal_is_used_when_path_is_generic: verifies the behavior described by "metadata family signal is used when path is generic",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for metadata family signal is used when path is generic,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_metadata_family_signal_is_used_when_path_is_generic(self):
        result = classify_model(
            'models/checkpoints/model.safetensors',
            metadata={'modelspec.architecture': 'stable-diffusion-xl-v1-base'},
        )
        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertIn('metadata modelspec.architecture', result.family_reason)

    # {
    #   責務: [test_conflicts_remain_unknown: verifies the behavior described by "conflicts remain unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for conflicts remain unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_conflicts_remain_unknown(self):
        result = classify_model(
            'models/checkpoints/flux-dev.safetensors',
            metadata={'ss_base_model_version': 'sdxl_base_v1-0'},
        )
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertIn('Conflicting family signals', result.family_reason)

    # {
    #   責務: [
    #     test_kind_comes_from_directory_or_declared_value: verifies the behavior described by "kind comes from directory or declared value",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for kind comes from directory or declared value,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_kind_comes_from_directory_or_declared_value(self):
        self.assertEqual(classify_model('models/Lora/character.safetensors').kind, ModelKind.LORA)
        self.assertEqual(classify_model('character.safetensors', declared_kind='vae').kind, ModelKind.VAE)

    # {
    #   責務: [test_ambiguous_kind_remains_unknown: verifies the behavior described by "ambiguous kind remains unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for ambiguous kind remains unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_ambiguous_kind_remains_unknown(self):
        result = classify_model('models/checkpoints/loras/model.safetensors')
        self.assertEqual(result.kind, ModelKind.UNKNOWN)
        self.assertIn('Conflicting model directory kinds', result.kind_reason)

    # {
    #   責務: [test_unmarked_family_stays_unknown: verifies the behavior described by "unmarked family stays unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for unmarked family stays unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unmarked_family_stays_unknown(self):
        result = classify_model('models/checkpoints/shiitakeMix_v20.safetensors')
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)


# {
#   責務: [SafetensorsMetadataTests: related test fixtures and cases for SafetensorsMetadata behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SafetensorsMetadataTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_reads_metadata_without_loading_tensor_payload: verifies the behavior described by "reads metadata without loading tensor payload",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for reads metadata without loading tensor payload,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_reads_metadata_without_loading_tensor_payload(self):
        metadata = {'modelspec.architecture': 'stable-diffusion-xl-v1-base'}
        header = json.dumps({'__metadata__': metadata, 'weight': {'dtype': 'F16'}}).encode('utf-8')
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / 'model.safetensors'
            path.write_bytes(struct.pack('<Q', len(header)) + header + b'tensor payload')
            parsed_metadata = read_safetensors_metadata(path)
            self.assertEqual(parsed_metadata, metadata)
            self.assertEqual(classify_model(path, metadata=parsed_metadata).family, ModelFamily.SDXL)

    # {
    #   責務: [test_rejects_truncated_header: verifies the behavior described by "rejects truncated header"]
    #   処理: [
    #     1: arrange case data and fixture state for rejects truncated header,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_rejects_truncated_header(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / 'broken.safetensors'
            path.write_bytes(struct.pack('<Q', 20) + b'{}')
            with self.assertRaises(SafetensorsMetadataError):
                read_safetensors_metadata(path)


if __name__ == '__main__':
    unittest.main()
