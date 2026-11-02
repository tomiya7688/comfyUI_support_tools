from __future__ import annotations

import io
import json
import struct
import unittest
from unittest.mock import patch

from src.comfyui_support_tools.shared.safetensors_metadata import (
    SafetensorsMetadataError, read_safetensors_evidence,
)


# {
#   責務: [_file_bytes: serializes JSON header bytes with the safetensors length prefix]
#   処理: [1: serialize the fixture JSON header, 2: prefix its length using the safetensors format]
#   引数: [header: safetensors header mapping (dict)]
#   戻り値: [result: tuple[bytes, int] produced for the supplied fixture/input]
# }
def _file_bytes(header: dict) -> tuple[bytes, int]:
    data = json.dumps(header).encode("utf-8")
    return struct.pack("<Q", len(data)) + data, len(data)


# {
#   責務: [SafetensorsEvidenceTests: related test fixtures and cases for SafetensorsEvidence behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SafetensorsEvidenceTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_reads_only_header_not_tensor_payload: verifies the behavior described by "reads only header not tensor payload",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for reads only header not tensor payload,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: raw_read built or selected by this helper]
    # }
    def test_reads_only_header_not_tensor_payload(self):
        prefix, length = _file_bytes({"__metadata__": {"architecture": "sdxl"}, "weight": {"shape": [640, 2048]}})
        source = io.BytesIO(prefix + b"tensor payload must not be read")
        raw_read = source.read
        sizes = []

        # {
        #   責務: [guarded_read: records requested tensor-byte reads and delegates only within the allowed header range]
        #   処理: [1: record the requested read size, 2: delegate the read and return only the allowed header bytes]
        #   引数: [size: number of bytes requested by the guarded stream read (unspecified)]
        #   戻り値: [result: raw_read built or selected by this helper]
        # }
        def guarded_read(size):
            self.assertLessEqual(source.tell() + size, len(prefix))
            sizes.append(size)
            return raw_read(size)

        with patch.object(source, "read", side_effect=guarded_read), patch("pathlib.Path.open", return_value=source):
            metadata, shapes = read_safetensors_evidence("model.safetensors")
        self.assertEqual(sizes, [8, length])
        self.assertEqual(metadata, {"architecture": "sdxl"})
        self.assertEqual(shapes, {"weight": (640, 2048)})

    # {
    #   責務: [
    #     test_invalid_shape_descriptors_are_rejected: verifies the behavior described by "invalid shape descriptors are rejected",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for invalid shape descriptors are rejected,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_invalid_shape_descriptors_are_rejected(self):
        for descriptor in [None, {"shape": "2048"}, {"shape": [True, 2048]}, {"shape": [-1, 2048]}, {}]:
            with self.subTest(descriptor=descriptor):
                data, _ = _file_bytes({"weight": descriptor})
                with patch("pathlib.Path.open", return_value=io.BytesIO(data)):
                    with self.assertRaisesRegex(SafetensorsMetadataError, "shape"):
                        read_safetensors_evidence("model.safetensors")

    # {
    #   責務: [
    #     test_empty_and_scalar_tensors_are_valid_header_descriptors: verifies the behavior described by "empty and scalar tensors are valid header descriptors",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for empty and scalar tensors are valid header descriptors,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_empty_and_scalar_tensors_are_valid_header_descriptors(self):
        data, _ = _file_bytes({"scalar": {"shape": []}, "empty": {"shape": [0, 2048]}})
        with patch("pathlib.Path.open", return_value=io.BytesIO(data)):
            _, shapes = read_safetensors_evidence("model.safetensors")
        self.assertEqual(shapes, {"scalar": (), "empty": (0, 2048)})

    # {
    #   責務: [
    #     test_oversized_header_is_rejected_before_reading_body: verifies the behavior described by "oversized header is rejected before reading body",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for oversized header is rejected before reading body,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_oversized_header_is_rejected_before_reading_body(self):
        source = io.BytesIO(struct.pack("<Q", 64 * 1024 * 1024 + 1))
        with patch.object(source, "read", wraps=source.read) as read, patch("pathlib.Path.open", return_value=source):
            with self.assertRaisesRegex(SafetensorsMetadataError, "exceeds"):
                read_safetensors_evidence("model.safetensors")
            self.assertEqual(read.call_args_list[0].args, (8,))
            self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
