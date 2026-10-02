from __future__ import annotations

import io
import json
import struct
import unittest
from unittest.mock import patch

from src.comfyui_support_tools.shared.safetensors_metadata import (
    SafetensorsMetadataError, read_safetensors_evidence,
)


def _file_bytes(header: dict) -> tuple[bytes, int]:
    data = json.dumps(header).encode("utf-8")
    return struct.pack("<Q", len(data)) + data, len(data)


class SafetensorsEvidenceTests(unittest.TestCase):
    def test_reads_only_header_not_tensor_payload(self):
        prefix, length = _file_bytes({"__metadata__": {"architecture": "sdxl"}, "weight": {"shape": [640, 2048]}})
        source = io.BytesIO(prefix + b"tensor payload must not be read")
        raw_read = source.read
        sizes = []

        def guarded_read(size):
            self.assertLessEqual(source.tell() + size, len(prefix))
            sizes.append(size)
            return raw_read(size)

        with patch.object(source, "read", side_effect=guarded_read), patch("pathlib.Path.open", return_value=source):
            metadata, shapes = read_safetensors_evidence("model.safetensors")
        self.assertEqual(sizes, [8, length])
        self.assertEqual(metadata, {"architecture": "sdxl"})
        self.assertEqual(shapes, {"weight": (640, 2048)})

    def test_invalid_shape_descriptors_are_rejected(self):
        for descriptor in [None, {"shape": "2048"}, {"shape": [True, 2048]}, {"shape": [-1, 2048]}, {}]:
            with self.subTest(descriptor=descriptor):
                data, _ = _file_bytes({"weight": descriptor})
                with patch("pathlib.Path.open", return_value=io.BytesIO(data)):
                    with self.assertRaisesRegex(SafetensorsMetadataError, "shape"):
                        read_safetensors_evidence("model.safetensors")

    def test_empty_and_scalar_tensors_are_valid_header_descriptors(self):
        data, _ = _file_bytes({"scalar": {"shape": []}, "empty": {"shape": [0, 2048]}})
        with patch("pathlib.Path.open", return_value=io.BytesIO(data)):
            _, shapes = read_safetensors_evidence("model.safetensors")
        self.assertEqual(shapes, {"scalar": (), "empty": (0, 2048)})

    def test_oversized_header_is_rejected_before_reading_body(self):
        source = io.BytesIO(struct.pack("<Q", 64 * 1024 * 1024 + 1))
        with patch.object(source, "read", wraps=source.read) as read, patch("pathlib.Path.open", return_value=source):
            with self.assertRaisesRegex(SafetensorsMetadataError, "exceeds"):
                read_safetensors_evidence("model.safetensors")
            self.assertEqual(read.call_args_list[0].args, (8,))
            self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
