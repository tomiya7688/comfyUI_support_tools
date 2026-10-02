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

The root can be overridden in `user_data/input/config/common/paths.json` with `models_root`; `checkpoints` and `comfy_flows` can be set separately. Existing explicit roots are not rewritten by the application.

## Existing installations

The application does not move, copy, or delete model weights automatically. Until a user verifies a migration, the catalog also scans legacy `models/checkpoints`, `models/diffusion_models`, `models/unet`, `models/Lora`, `models/loras`, `models/VAE`, `models/vae`, and the former top-level `checkpoints` directory. This preserves discoverability while the files remain where they are.

For a manual migration, keep the source intact while placing models into the recommended tree and verifying they appear in the generation tab for the selected backend. Only remove a source copy after confirming the destination file and generated image. Preserve customized `models_root` / `checkpoints` values in `paths.json`; do not replace them with defaults.

ComfyUI model-folder junctions can be inspected with:

```powershell
python tools/maintenance/sync_comfyui_model_links.py
```

This command is a preview by default and only proposes repairing broken links to matching directories under the configured shared root. `--apply` is an explicit operation that replaces only those broken directory links; it does not move model files. Review the preview before applying it.