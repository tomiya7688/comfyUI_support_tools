"""Focused capability-adapter contract tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.trainer_registry import (
    AdapterMethod,
    SimpleTunerAdapter,
    SupportLevel,
    TrainerProbe,
    architecture_profiles,
)


# {
# 責務: [TrainerRegistryAdapterTests: verify runtime adapter capability resolution]
# フィールド: [temporary manifest roots and architecture profiles]
# 処理: [exercise manifest overrides and unavailable-profile behavior independently]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report adapter contract]
# }
class TrainerRegistryAdapterTests(unittest.TestCase):
    # {
    # 責務: [setUp: prepare a probed adapter with a deterministic capability manifest]
    # 処理: [set a valid trainer identity and runtime profile declaration]
    # 引数: [self: test fixture]
    # 戻り値: [None: adapter is ready]
    # }
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profiles = architecture_profiles()
        self.adapter = SimpleTunerAdapter(
            self.root, executable="unused", profiles=self.profiles, available_vram_gib=24
        )
        self.adapter._probe_cache = TrainerProbe(
            "simpletuner", True, "1.2.3", str(self.root), "fixture", "fingerprint"
        )
        self.adapter._manifest = {"models": ["sdxl"]}

    # {
    # 責務: [tearDown: remove the isolated temporary manifest root]
    # 処理: [clean up local test files]
    # 引数: [self: test fixture]
    # 戻り値: [None: temporary files removed]
    # }
    def tearDown(self):
        self.temp.cleanup()

    # {
    # 責務: [test_manifest_method_override_is_applied_to_runtime_matrix: honor explicit runtime levels]
    # 処理: [override profile method support and preserve other profile declarations]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_manifest_method_override_is_applied_to_runtime_matrix(self):
        self.adapter._manifest["methods"] = {"sdxl": {"lora": "unsupported"}}
        methods = {entry.method: entry.level for entry in self.adapter.supported_methods("sdxl")}
        self.assertEqual(methods[AdapterMethod.LORA], SupportLevel.UNSUPPORTED)
        self.assertIn(AdapterMethod.LOHA, methods)

    # {
    # 責務: [test_unknown_or_undeclared_profile_is_unsupported: fail closed on absent profiles]
    # 処理: [ensure unknown and unlisted architecture names never gain runtime support]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_unknown_or_undeclared_profile_is_unsupported(self):
        for architecture in ("unknown", "flux1"):
            with self.subTest(architecture=architecture):
                methods = self.adapter.supported_methods(architecture)
                self.assertTrue(methods)
                self.assertTrue(all(entry.level is SupportLevel.UNSUPPORTED for entry in methods))

    # {
    # 責務: [test_manifest_parser_rejects_invalid_capability_levels: validate external declarations]
    # 処理: [reject malformed support levels before they affect capability decisions]
    # 引数: [self: test case]
    # 戻り値: [None: invalid manifest raises ValueError]
    # }
    def test_manifest_parser_rejects_invalid_capability_levels(self):
        from comfyui_support_tools.shared.trainer_registry.adapters import _read_manifest

        (self.root / "codex_capabilities.json").write_text(
            json.dumps({"methods": {"sdxl": {"lora": "maybe"}}}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "support levels"):
            _read_manifest(self.root)


if __name__ == "__main__":
    unittest.main()
