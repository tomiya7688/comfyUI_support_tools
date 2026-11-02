[日本語](lora_dataset_curator.md) | [Documentation index](README.md)

# LoRA Dataset Curator / Caption Planner

`comfyui_support_tools.applications.lora_dataset_curator` creates one reproducible curation plan for image inventory, caption ownership, duplicate groups, coverage, duplicate-safe validation splits, and sample weights. Launch the review window with:

```bash
python -m comfyui_support_tools.applications.lora_dataset_curator
```

Choose a task, caption policy, crop policy, validation ratio, and seed, then analyze the dataset. Double-click an image row to cycle `keep` / `low_weight` / `exclude`. For the selected image, you can edit concept-owned tags, variable tags, weight, and split. A split override on one image applies to its whole duplicate group; contradictory assignments and changes that leave no training group are rejected. The export destination must be new.

Adjacent `.txt` or `.caption` sidecars are reused for tags and captions. No built-in vision tagger runs. Callers can inject `ImageEvidenceProvider` and `EmbeddingSimilarityProvider` adapters for face/body/concept evidence or embedding similarity. Default quality values are Pillow-measured proxies for blur sharpness, 8-pixel-boundary blocking, and aspect preservation. The perceptual hash is a 64-bit average hash and does not replace a measured similarity model or human review. Images and sidecars are read-only; supported images are limited to 256 MiB each, inventory to 20,000 images, and near-candidate search to 5,000,000 comparisons.

Character training keeps identity/hair/accessories concept-owned and places pose/viewpoint/background/expression and clothing in variable captions by default. Character Registry accepted/rejected traits, per-image outfits, and variable attributes are applied. Clothing moves into identity only when the user enables `fixed_clothing`. Style keeps subject/context variation, while Object owns the target object. Known tag aliases are normalized; unknown words remain subject tags.

Use `DatasetCuratorApplication.curate(root, config, ...)` for analysis, optionally connect a local #55 trainer probe through `compare_caption_policies(analysis, probe)`, and call `export(analysis, destination, trainer)` after review. `SampleOverride` can change action, weight, train/validation assignment, and caption ownership. The export contains standard `train/` and `validation/` image/caption pairs, separate regularization images, `dataset_manifest.json`, and trainer configuration templates. Review model-specific resolution settings in the sd-scripts TOML. The SimpleTuner and AI Toolkit JSON files are dataset starter templates. Per-sample weights and crop policy are recorded in the manifest; trainer adapters must explicitly consume them for the trainer to apply them.

The curation fingerprint includes source SHA-256 values, caption variants, classification evidence, duplicate groups, configuration, overrides, splits, weights, and regularization images. Export copies images into an isolated staging directory, verifies source fingerprints, and renames the completed tree to a new destination. It never edits the input images or captions.

`tests/test_dataset_curator.py` covers task-specific caption ownership, Character Registry evidence, duplicate leakage prevention, manual group splits, Auto overrides, fingerprints, exports for all three trainers, regularization copies, and the #55 probe. Unit tests pass. Interactive GUI use, training with installed trainers, model-based automatic captioning, and third-party vision/embedding providers have not been validated in this checkout.
