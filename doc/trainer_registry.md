# Modern Trainer Adapter Registry

[English](trainer_registry.en.md) | [日本語](trainer_registry.md)

`comfyui_support_tools.shared.trainer_registry` はtrainer非依存の `TrainingSpec`、model別の `ArchitectureProfile`、runtime trainer probe、version付きcapability registryを分離します。SimpleTuner JSON、AI ToolkitのYAML互換process config、sd-scripts TOML/CLIへ変換するadapterを備えます。LyCORIS methodはsupported / experimental / unsupportedを区別します。Autoはsupported methodだけを選択し、manual固定の場合はexperimentalを許可します。unsupportedは常に拒否します。

profileはSDXL anime、FLUX.1、FLUX.2 dev/Klein 9B/Klein 4B、Qwen Image/2.1/Edit、SD3.5、Anima、Hunyuan Image、Krea2、HiDreamを区別します。text encoder、latent format、target block、schedule、dataset kind、text encoder train可否、trainer version、precision、trainer別quantization/offload feature、概算VRAMを宣言します。local safetensors headerまたはtrainer capability manifestから実在するtarget module名を取得でき、未存在のtargetはconfig validationで拒否します。

trainerの利用可否はlocal version probeと、checkout内に任意配置する `codex_capabilities.json` からruntimeで判断します。manifestではmodel/method/precision/quantization/target module/memory featureを制限できます。trainer versionまたはmanifestが変わるとcapability fingerprintも変わり、該当trainer/profileのcache行を差し替えます。smoke commandは `{executable}`、`{config}`、`{steps}`、`{output}` placeholderを含むargv listとして明示指定します。smokeは1〜8 stepに制限し、checkpointと生成sampleの両方が保存されたときだけfull-training gateを通過します。shell文字列は実行しません。

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

profile/cacheを追加しても外部trainerをinstall/updateしません。このruntimeではSimpleTuner、AI Toolkit、sd-scriptsの実環境を確認できないため、live capabilityやmodel-load成功を確認済みとはしていません。importやvalidation時に学習は開始しません。利用時はlocal model weight、captionまたはpaired-reference dataset、trainer checkout、依存library、検証済みsmoke manifestが必要です。VRAM値は保守的な目安で、実行可能性を保証しません。

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
