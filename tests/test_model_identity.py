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


class ModelIdentityTests(unittest.TestCase):
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

    def test_metadata_family_signal_is_used_when_path_is_generic(self):
        result = classify_model(
            'models/checkpoints/model.safetensors',
            metadata={'modelspec.architecture': 'stable-diffusion-xl-v1-base'},
        )
        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertIn('metadata modelspec.architecture', result.family_reason)

    def test_conflicts_remain_unknown(self):
        result = classify_model(
            'models/checkpoints/flux-dev.safetensors',
            metadata={'ss_base_model_version': 'sdxl_base_v1-0'},
        )
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertIn('Conflicting family signals', result.family_reason)

    def test_kind_comes_from_directory_or_declared_value(self):
        self.assertEqual(classify_model('models/Lora/character.safetensors').kind, ModelKind.LORA)
        self.assertEqual(classify_model('character.safetensors', declared_kind='vae').kind, ModelKind.VAE)

    def test_ambiguous_kind_remains_unknown(self):
        result = classify_model('models/checkpoints/loras/model.safetensors')
        self.assertEqual(result.kind, ModelKind.UNKNOWN)
        self.assertIn('Conflicting model directory kinds', result.kind_reason)

    def test_unmarked_family_stays_unknown(self):
        result = classify_model('models/checkpoints/shiitakeMix_v20.safetensors')
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)


class SafetensorsMetadataTests(unittest.TestCase):
    def test_reads_metadata_without_loading_tensor_payload(self):
        metadata = {'modelspec.architecture': 'stable-diffusion-xl-v1-base'}
        header = json.dumps({'__metadata__': metadata, 'weight': {'dtype': 'F16'}}).encode('utf-8')
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / 'model.safetensors'
            path.write_bytes(struct.pack('<Q', len(header)) + header + b'tensor payload')
            parsed_metadata = read_safetensors_metadata(path)
            self.assertEqual(parsed_metadata, metadata)
            self.assertEqual(classify_model(path, metadata=parsed_metadata).family, ModelFamily.SDXL)

    def test_rejects_truncated_header(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / 'broken.safetensors'
            path.write_bytes(struct.pack('<Q', 20) + b'{}')
            with self.assertRaises(SafetensorsMetadataError):
                read_safetensors_metadata(path)


if __name__ == '__main__':
    unittest.main()
