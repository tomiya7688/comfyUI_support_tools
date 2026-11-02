"""Tests for runtime-aware architecture and trainer capability resolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import tomllib

from comfyui_support_tools.shared.trainer_registry import (
    AdapterMethod,
    AIToolkitAdapter,
    Quantization,
    SdScriptsAdapter,
    SimpleTunerAdapter,
    SmokeGatedTraining,
    SmokeTestRunner,
    SupportLevel,
    TrainerProbe,
    TrainerSupportRegistry,
    TrainingSpec,
    architecture_profiles,
)


# {
# 責務: [TrainerRegistryTests: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class TrainerRegistryTests(unittest.TestCase):
    # {
    # 責務: [setUp: prepare a local fake trainer executable and capability manifest]
    # 処理: [expose deterministic runtime version, architecture, method and smoke behavior]
    # 引数: [self: test fixture]
    # 戻り値: [None: local test installation ready]
    # }
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.base_model = self.root / "base-model"
        self.base_model.mkdir()
        self.executable = self.root / "fake-trainer"
        self._write_executable("1.2.3", succeed=True)
        self.manifest = self.root / "codex_capabilities.json"
        self._write_manifest()
        self.profiles = architecture_profiles()
        self.adapter = SimpleTunerAdapter(
            self.root,
            str(self.executable),
            profiles=self.profiles,
            available_vram_gib=24,
        )
        self.adapter.required_modules = ()

    # {
    # 責務: [tearDown: remove temporary trainer fixture]
    # 処理: [delete test files after each isolated case]
    # 引数: [self: test fixture]
    # 戻り値: [None: temporary files removed]
    # }
    def tearDown(self):
        self.temp.cleanup()

    # {
    # 責務: [_write_executable: create a shell-free fake trainer command]
    # 処理: [return version output and optionally create checkpoint/sample smoke outputs]
    # 引数: [self: test fixture, version: emitted trainer version, succeed: smoke result]
    # 戻り値: [None: executable replaced]
    # }
    def _write_executable(self, version, succeed):
        script = f"""#!/usr/bin/env python3
import pathlib, sys
if '--version' in sys.argv:
    print('SimpleTuner {version}')
elif '--smoke' in sys.argv:
    if {succeed!r}:
        output = pathlib.Path(sys.argv[sys.argv.index('--smoke') + 1])
        (output / 'smoke.safetensors').write_bytes(b'checkpoint')
        (output / 'sample.png').write_bytes(b'image')
    sys.exit(0 if {succeed!r} else 2)
else:
    sys.exit(2)
"""
        self.executable.write_text(script, encoding="utf-8")
        self.executable.chmod(self.executable.stat().st_mode | 0o111)

    # {
    # 責務: [_write_manifest: persist trainer capability information for runtime probing]
    # 処理: [declare only one compatible model, an experimental method and a short smoke argv]
    # 引数: [self: test fixture]
    # 戻り値: [None: capability manifest updated]
    # }
    def _write_manifest(self):
        self.manifest.write_text(
            json.dumps(
                {
                    "models": ["sdxl"],
                    "methods": {"sdxl": {"loha": "experimental"}},
                    "target_modules": {"sdxl": ["unet.down_blocks.0.attn.to_q"]},
                    "smoke_command": ["{executable}", "--smoke", "{output}"],
                }
            ),
            encoding="utf-8",
        )

    # {
    # 責務: [_spec: create a valid neutral SDXL training request]
    # 処理: [use discovered targets and supported precision/memory options]
    # 引数: [self: test fixture, architecture: profile key]
    # 戻り値: [TrainingSpec: isolated common trainer request]
    # }
    def _spec(self, architecture="sdxl"):
        return TrainingSpec(
            architecture=architecture,
            method=AdapterMethod.LORA,
            base_model=self.base_model,
            dataset=self.dataset,
            output=self.root / "training-output",
            steps=100,
            rank=8,
            alpha=8,
            target_modules=("unet.down_blocks.0.attn.to_q",),
        )

    # {
    # 責務: [test_runtime_probe_rejects_missing_trainer_and_fingerprints_version: detect installation changes]
    # 処理: [verify installation probe and runtime version changes update the capability fingerprint]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_runtime_probe_rejects_missing_trainer_and_fingerprints_version(self):
        first = self.adapter.probe()
        self.assertTrue(first.available, first.reason)
        self._write_executable("1.2.4", succeed=True)
        second = self.adapter.probe()
        self.assertNotEqual(first.capability_fingerprint, second.capability_fingerprint)
        missing = SimpleTunerAdapter(
            "/no/such/trainer", executable="definitely-not-a-trainer", profiles=self.profiles
        )
        self.assertFalse(missing.probe().available)

    # {
    # 責務: [test_auto_skips_experimental_but_manual_pin_allows_it: respect support levels]
    # 処理: [select supported LoRA automatically while requiring manual pin for experimental LoHa]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_auto_skips_experimental_but_manual_pin_allows_it(self):
        registry = TrainerSupportRegistry((self.adapter,), self.profiles)
        automatic = registry.resolve("sdxl", AdapterMethod.LOHA)
        manual = registry.resolve("sdxl", AdapterMethod.LOHA, "SimpleTuner")
        self.assertIsNone(automatic.selected)
        self.assertEqual(manual.selected, "simpletuner")
        self.assertEqual(manual.level, SupportLevel.EXPERIMENTAL)

    # {
    # 責務: [_prime_adapter: provide a deterministic runtime capability for translation tests]
    # 処理: [inject an already-probed fake installation and exact discovered targets]
    # 引数: [self: test fixture, adapter: trainer adapter, trainer_name: runtime identity]
    # 戻り値: [None: fake adapter ready]
    # }
    def _prime_adapter(self, adapter, trainer_name):
        adapter._probe_cache = TrainerProbe(
            trainer_name, True, "1.2.3", "/fake/trainer", "fixture", "fingerprint"
        )
        adapter._manifest = {
            "models": ["sdxl"],
            "target_modules": {"sdxl": ["unet.down_blocks.0.attn.to_q"]},
        }

    # {
    # 責務: [test_runtime_cache_invalidates_when_manifest_changes: refresh on trainer capability updates]
    # 処理: [write two versions of a capability manifest and retain only the latest trainer/profile cache]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_runtime_cache_invalidates_when_manifest_changes(self):
        cache = self.root / "matrix.json"
        registry = TrainerSupportRegistry((self.adapter,), self.profiles, cache)
        first = registry.support_matrix("sdxl")[0]
        self.assertEqual(first.target_modules, ("unet.down_blocks.0.attn.to_q",))
        self.manifest.write_text(
            json.dumps(
                {"models": ["sdxl"], "target_modules": {"sdxl": ["unet.mid_block.attn.to_q"]}}
            ),
            encoding="utf-8",
        )
        second = registry.support_matrix("sdxl")[0]
        self.assertNotEqual(first.capability_fingerprint, second.capability_fingerprint)
        self.manifest.write_text(
            json.dumps({"models": ["sdxl"], "minimum_versions": {"sdxl": "9.0.0"}}),
            encoding="utf-8",
        )
        too_old = registry.resolve("sdxl", AdapterMethod.LORA)
        self.assertIsNone(too_old.selected)
        data = json.loads(cache.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)

    # {
    # 責務: [test_common_spec_translates_to_json_yaml_and_toml: keep trainer formats behind adapters]
    # 処理: [translate one neutral spec through SimpleTuner, AI Toolkit and sd-scripts format adapters]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_common_spec_translates_to_json_yaml_and_toml(self):
        spec = self._spec()
        self.assertTrue(self.adapter.validate_config(spec).valid)
        simple_config = self.adapter.translate_config(spec)
        self.assertEqual(simple_config["network_dim"], 8)
        toolkit = AIToolkitAdapter(profiles=self.profiles)
        toolkit.required_modules = ()
        self._prime_adapter(toolkit, "ai_toolkit")
        toolkit_config = toolkit.translate_config(spec)
        yaml_as_json = toolkit.serialize_config(toolkit_config)
        self.assertIn('"type": "sd_trainer"', yaml_as_json)
        sd_scripts = SdScriptsAdapter(profiles=self.profiles)
        sd_scripts.required_modules = ()
        self._prime_adapter(sd_scripts, "sd_scripts")
        toml_as_text = sd_scripts.serialize_config(simple_config)
        parsed = tomllib.loads(toml_as_text)
        self.assertEqual(parsed["network_dim"], 8)
        self.assertIn("--network_dim", sd_scripts.to_cli(spec))

    # {
    # 責務: [test_profile_variants_keep_model_specific_training_contracts: avoid cross-model preset reuse]
    # 処理: [verify FLUX.2 variants and Qwen edit use distinct text, latent, schedule and dataset fields]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_profile_variants_keep_model_specific_training_contracts(self):
        profiles = architecture_profiles()
        self.assertNotEqual(
            profiles["flux2_klein_9b"].text_encoder, profiles["flux2_klein_4b"].text_encoder
        )
        self.assertNotEqual(
            profiles["flux2_dev"].latent_format, profiles["flux2_klein_4b"].latent_format
        )
        self.assertEqual(profiles["qwen_image_edit"].dataset_kind, "paired_reference_edit")
        self.assertEqual(profiles["qwen_image_2_1"].training_schedule, "multistage_flow_matching")
        self.assertNotIn(Quantization.NF4, profiles["qwen_image"].quantization["simpletuner"])

    # {
    # 責務: [test_smoke_failure_blocks_full_training_and_success_requires_artifacts: gate full jobs]
    # 処理: [require a short external run to save a checkpoint and sample before callback execution]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_smoke_failure_blocks_full_training_and_success_requires_artifacts(self):
        gate = SmokeGatedTraining(SmokeTestRunner(steps=2, timeout_seconds=20))
        started = []
        result, full = gate.start(self.adapter, self._spec(), lambda *_: started.append(True))
        self.assertTrue(result.passed, result.reason)
        self.assertTrue(result.checkpoint.is_file())
        self.assertTrue(result.sample.is_file())
        self.assertIsNone(full)
        self.assertEqual(started, [True])
        self._write_executable("1.2.3", succeed=False)
        failed, blocked = gate.start(self.adapter, self._spec(), lambda *_: started.append(False))
        self.assertFalse(failed.passed)
        self.assertIsNone(blocked)
        self.assertEqual(started, [True])

    # {
    # 責務: [test_dataset_kind_and_trainer_feature_limits_are_enforced: preserve model-specific needs]
    # 処理: [reject Qwen edit caption-only data and unsupported sd-scripts CPU offload]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_dataset_kind_and_trainer_feature_limits_are_enforced(self):
        toolkit = AIToolkitAdapter(profiles=self.profiles)
        self._prime_adapter(toolkit, "ai_toolkit")
        toolkit._manifest = {
            "models": ["qwen_image_edit"],
            "target_modules": {"qwen_image_edit": ["transformer_blocks.*.attn.*"]},
        }
        qwen_edit = self._spec("qwen_image_edit")
        qwen_edit = TrainingSpec(
            **{
                **vars(qwen_edit),
                "method": AdapterMethod.LORA,
                "target_modules": ("transformer_blocks.*.attn.*",),
                "dataset_kind": "image_caption",
            }
        )
        validation = toolkit.validate_config(qwen_edit)
        self.assertFalse(validation.valid)
        self.assertTrue(any("dataset kind" in error for error in validation.errors))

    # {
    # 責務: [test_local_model_target_discovery_uses_only_present_safetensors_modules: avoid stale target presets]
    # 処理: [inspect a model safetensors header and return module names present in that architecture]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_local_model_target_discovery_uses_only_present_safetensors_modules(self):
        if not __import__("importlib.util").util.find_spec("safetensors"):
            self.skipTest("optional safetensors package not installed")
        from safetensors.numpy import save_file

        model_path = self.root / "weights.safetensors"
        save_file(
            {
                "unet.down_blocks.0.attn.to_q.weight": __import__("numpy").zeros((2, 2)),
                "unet.down_blocks.0.attn.to_v.weight": __import__("numpy").zeros((2, 2)),
                "text_encoder.layers.0.weight": __import__("numpy").zeros((2, 2)),
            },
            str(model_path),
        )
        self.adapter.probe()
        self.adapter._manifest = {"models": ["sdxl"]}
        self.assertEqual(
            self.adapter.target_modules("sdxl", model_path),
            ("unet.down_blocks.0.attn.to_q", "unet.down_blocks.0.attn.to_v"),
        )

    # {
    # 責務: [test_recipe_provenance_records_safe_upstream_and_versioned_config_hash: retain origin evidence]
    # 処理: [hash translated configuration and strip credential-bearing upstream URL components]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_recipe_provenance_records_safe_upstream_and_versioned_config_hash(self):
        self.adapter.upstream_repository = self.adapter._sanitize_repository(
            "https://user:password@github.com/example/trainer.git?token=secret"
        )
        provenance = self.adapter.training_provenance(self._spec())
        self.assertEqual(provenance.upstream_repository, "https://github.com/example/trainer")
        self.assertEqual(provenance.trainer_version, "SimpleTuner 1.2.3")
        self.assertEqual(len(provenance.source_recipe_sha256), 64)
        self.assertNotIn("password", repr(provenance))


if __name__ == "__main__":
    unittest.main()
