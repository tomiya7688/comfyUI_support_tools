# Modern Trainer Adapter Registry

[English](trainer_registry.en.md) | [日本語](trainer_registry.md)

`comfyui_support_tools.shared.trainer_registry` keeps a trainer-neutral `TrainingSpec`, model-specific `ArchitectureProfile`, runtime trainer probe, and versioned capability registry separate. Built-in config adapters target SimpleTuner JSON, AI Toolkit YAML-compatible process config, and sd-scripts TOML/CLI. The LyCORIS method set distinguishes supported, experimental, and unsupported methods. Auto selects supported methods only; a manually pinned trainer may use an experimental method, while unsupported requests always fail.

Profiles distinguish SDXL anime, FLUX.1, FLUX.2 dev/Klein 9B/Klein 4B, Qwen Image/2.1/Edit, SD3.5, Anima, Hunyuan Image, Krea2 and HiDream. Each profile declares text encoder, latent format, target blocks, schedule, dataset kind, text-encoder policy, trainer versions, precision, per-trainer quantization/offload features and approximate minimum VRAM. A local safetensors header or trainer capability manifest can provide actual target-module names. Missing targets fail config validation.

Trainer availability is determined at runtime from a local version probe plus optional `codex_capabilities.json` in the trainer checkout. The manifest can restrict models, methods, precision, quantization, target modules and memory features; a version or manifest change changes the capability fingerprint and replaces that trainer/profile's cached matrix row. A smoke command must be explicitly declared as an argv list with `{executable}`, `{config}`, `{steps}` and `{output}` placeholders. The smoke runner limits work to 1–8 steps and requires both a nonempty checkpoint and generated sample before its gate invokes full training. It never executes shell strings.

```json
{
  "models": ["sdxl"],
  "minimum_versions": {"sdxl": "1.2.0"},
  "methods": {"sdxl": {"lora": "supported", "loha": "experimental"}},
  "target_modules": {"sdxl": ["unet.down_blocks.0.attn.to_q"]},
  "precision": {"sdxl": ["bf16", "fp16"]},
  "quantization": {"sdxl": ["none", "nf4"]},
  "features": {"sdxl": ["gradient_checkpointing", "vae_cache"]},
  "smoke_command": ["{executable}", "train", "--config", "{config}", "--steps", "{steps}", "--output", "{output}"]
}
```

The cache and profile declarations do not install or update third-party trainers. This runtime has no verified SimpleTuner, AI Toolkit or sd-scripts installation, so live capability and model-load checks cannot be claimed here. No training is started during import or validation. Local model weights, a caption or paired-reference dataset, trainer checkout, installed dependencies and a verified smoke manifest are required before use. VRAM estimation is conservative guidance, not a guarantee that a job fits.

```python
from pathlib import Path
from comfyui_support_tools.shared.trainer_registry import (
    AdapterMethod,
    default_trainer_registry,
)

registry = default_trainer_registry(
    trainer_roots={"simpletuner": Path("/opt/SimpleTuner")},
    cache_path=Path("trainer-support-cache.json"),
)
decision = registry.resolve("flux2_klein_4b", AdapterMethod.LORA, trainer="auto")
```
