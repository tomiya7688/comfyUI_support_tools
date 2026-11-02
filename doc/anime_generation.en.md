# Anime / Illustration Prompt Routing

[日本語](anime_generation.md)

Prompt Generate lets users select an anime use case (general / character / background / manga) and content profile (unspecified / SFW / NSFW). When a checkpoint name matches a registered profile, its Animagine XL, Illustrious XL, NoobAI XL, or general SDXL quality, intent, rating, and negative-tag policy is applied. Policy tags are deduplicated, and the selected profile, routing reason, and checkpoint are recorded in generation metadata.

Manual checkpoint selection is preserved by default. With optional Auto-route enabled, routing considers registered profiles in the local model catalog and enforces known prompt-LoRA family constraints. If a LoRA family cannot be identified, auto-routing stops instead of guessing. A manually selected checkpoint is also rejected when a known anime LoRA family is incompatible. Auto-route refuses ComfyUI workflows with explicit node model overrides.

`AnimeModelRegistry` stores aliases, family IDs, lineage, native resolution, prompt policy, compatible LoRA families, license references, training-base suitability, and declared use-case fit as profile data. Adding another family does not require a new branch in routing algorithms or the existing generic model classifier. The benchmark helper renders common cases with each family's own policy and records the exact input used for later output comparison.

## Validation scope and limitations

- Built-in policies are initial descriptors. They do not yet have a baseline, validation set, metric, or before/after prompt-quality comparison using real Animagine, Illustrious, or NoobAI checkpoints. Routing ranks declared use-case fit only and does not claim an image-quality winner.
- License references point to model-card URLs. License text/version and usage terms are not downloaded or verified, and training-base suitability remains `unknown`. Check the terms for the exact model version before redistribution or training.
- Character/background intents reach the prompt layer, but dedicated handoffs to Character Generator, Landscape generation, the #55 LoRA Method Selector, the #20 Evaluator, or Workflow Presets are not connected. Output quality with real models, LoRAs, and workflows is unverified.
- Unknown model families, unregistered checkpoints, and LoRAs without family evidence are never treated as compatible automatically. Unregistered checkpoints keep their manually selected name and prompt unchanged.

Tests cover adding a family descriptor, prompt-tag order/deduplication, use-case routing, known LoRA compatibility, explicit selection, family-specific benchmark prompt construction, and delivery of the resolved prompt/model to the generation adapter.
