"""Tests for descriptor identity, compatibility adapters, and extensions."""

from __future__ import annotations

import unittest
from dataclasses import replace

from scripts.tool_registry import TOOL_REGISTRY, ToolDescriptor, ToolRegistry


# {
#   責務: [FakeToolExtension: fake登録からimplementation bindingを検証する]
#   フィールド: []
# }
class FakeToolExtension:
    pass


# {
#   責務: [ToolRegistryTests: stable descriptor追加と重複拒否を検証する]
#   フィールド: [one fake extension descriptor]
# }
class ToolRegistryTests(unittest.TestCase):
    # {
    #   責務: [test_fake_extension_needs_one_descriptor_and_binding: fake toolが1登録で表示/settings/bindingを供給する]
    #   処理: [1: fake descriptor registryを作る 2: metadataと遅延implementation bindingを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_fake_extension_needs_one_descriptor_and_binding(self):
        descriptor = ToolDescriptor(
            "fake_tool",
            "Fake Tool",
            "Testing",
            "test.fake_tool",
            "tests.test_tool_registry:FakeToolExtension",
            "FakeToolExtension",
        )
        registry = ToolRegistry((descriptor,))
        self.assertEqual(registry.descriptors, (descriptor,))
        self.assertEqual(
            registry.settings_id_for_legacy_class("FakeToolExtension"), "test.fake_tool"
        )
        self.assertIs(registry.load_implementation(descriptor), FakeToolExtension)

    # {
    #   責務: [test_duplicate_descriptor_ids_and_settings_ids_are_rejected: conflicting central metadataをfail-fastする]
    #   処理: [1: duplicate identity casesを作る 2: registry validation errorを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_duplicate_descriptor_ids_and_settings_ids_are_rejected(self):
        first = ToolDescriptor(
            "a",
            "A",
            "Test",
            "test.a",
            "tests.test_tool_registry:FakeToolExtension",
            "SharedLegacyTab",
        )
        duplicate_id = replace(first, settings_id="test.b")
        duplicate_settings = replace(first, id="b")
        with self.assertRaises(ValueError):
            ToolRegistry((first, duplicate_id))
        with self.assertRaises(ValueError):
            ToolRegistry((first, duplicate_settings))

        duplicate_legacy_name = replace(first, id="c", settings_id="test.c")
        with self.assertRaises(ValueError):
            ToolRegistry((first, duplicate_legacy_name))

    # {
    #   責務: [test_renaming_legacy_class_does_not_change_stable_ids: class-name migration adapterをstable identityと分離する]
    #   処理: [1: descriptor legacy classだけを変更する 2: stable ID/settings IDを保持することを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_renaming_legacy_class_does_not_change_stable_ids(self):
        descriptor = TOOL_REGISTRY.descriptors[0]
        renamed_adapter = replace(descriptor, legacy_class="RenamedLegacyTab")
        registry = ToolRegistry((renamed_adapter,))
        self.assertEqual(renamed_adapter.id, descriptor.id)
        self.assertEqual(renamed_adapter.settings_id, descriptor.settings_id)
        self.assertEqual(
            registry.settings_id_for_legacy_class("RenamedLegacyTab"), descriptor.settings_id
        )


if __name__ == "__main__":
    unittest.main()
