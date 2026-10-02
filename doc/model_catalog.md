# Shared model catalog and safe transition

The default shared model root is `user_data/input/models`. New installations use this root for model choices; an existing `paths.json` value remains authoritative. If a legacy config has `input_models` but no `models_root`, that configured `input_models` value is retained.

## Recommended layout

```text
user_data/input/models/
├── checkpoints/
│   ├── sd15/
│   ├── sdxl/
│   ├── flux/
│   └── anima/
├── diffusion_models/     # ComfyUI UNets
├── loras/
├── vae/
└── flows/                # API-format ComfyUI workflow JSON, not model weights
```

Family subfolders are optional but help identify models whose filenames and metadata do not state their family. Checkpoints, UNets, LoRAs, and VAEs are cataloged separately. A1111 and ComfyUI API choices are merged with local choices; duplicate names are removed.

Selected checkpoints/UNets and prompt LoRAs are resolved against configured shared, legacy, and active-backend model folders. Their Safetensors headers supply family metadata and tensor-layout evidence without loading tensor weights. Only compact classification results are cached, keyed by path, modification time, size, and declared model kind. Distinct local files with the same catalog name remain `unknown`; directory links to the same physical path are deduplicated. Invalid headers keep filename/path evidence and report why metadata was unavailable. Compatibility logs include the family evidence for both models. Formats such as `.ckpt` are not deserialized for classification.

The supported tensor signatures and their primary-source references are documented in [model_structure.md](model_structure.md). Naming, metadata, and structural contradictions remain `unknown`. Structural compatibility describes the architecture family, not an exact training release or guaranteed compatibility with every tensor in a particular LoRA.

A1111 checkpoint display names may include a hexadecimal hash suffix; this display suffix is removed for local lookup. Extensionless LoRA API aliases are resolved to model filenames, including unique matches in subfolders. Multiple physical files matching an alias remain `unknown`.

The root can be overridden in `user_data/input/config/common/paths.json` with `models_root`; `checkpoints` and `comfy_flows` can be set separately. Existing explicit roots are not rewritten by the application.

## Existing installations

The application does not move, copy, or delete model weights automatically. Until a user verifies a migration, the catalog also scans legacy `models/checkpoints`, `models/diffusion_models`, `models/unet`, `models/Lora`, `models/loras`, `models/VAE`, `models/vae`, and the former top-level `checkpoints` directory. This preserves discoverability while the files remain where they are.

Workflows listed from `models/flows` are resolved from that legacy folder when absent from the configured workflow root. A configured copy takes precedence. Model-input inspection, workflow-derived choices, and generation use the same resolved file.

For a manual migration, keep the source intact while placing models into the recommended tree and verifying they appear in the generation tab for the selected backend. Only remove a source copy after confirming the destination file and generated image. Preserve customized `models_root` / `checkpoints` values in `paths.json`; do not replace them with defaults.

ComfyUI model-folder junctions can be inspected with:

```powershell
python tools/maintenance/sync_comfyui_model_links.py
```

This command is a preview by default and only proposes repairing broken links to matching directories under the configured shared root. `--apply` is an explicit operation that replaces only those broken directory links; it does not move model files. Review the preview before applying it.
