# LoRA Composition Lab

[English](lora_composition.en.md) | [日本語](lora_composition.md)

`comfyui_support_tools.shared.lora_composition` provides an optional CPU-side backend for reviewing and composing compatible LoRA safetensors. Install `requirements-lora-composition.txt` in the host runtime; no model tensors are loaded during package import.

The API loads roles and source hashes, checks family/architecture/base identity and target modules, and reports missing provenance as an advisory. It computes per-layer update norms, cosine similarity, output-subspace overlap, sign conflict, layer overlap, and singular-value summaries. It supports weighted merge, a per-element top-K winner baseline, and a role-aware Zip-style conflict selector. Every static export is truncated to a configured rank and writes safe A/B tensors with model and source provenance. Static output refuses to overwrite existing files; a JSON runtime recipe is also saved without changing source LoRAs.

`search_scales` evaluates bounded global and per-layer candidate grids through a caller-provided generation/evaluation bridge. Each `EvaluationCase` pins the prompt and seed; score fields cover subject/style fidelity, prompt controllability, image quality, concept presence, confusion, binding, attribute swaps, leakage, and anatomy. Previous user scale selections are stored in an atomic bounded history file and added as search priors.

Example:

```python
from comfyui_support_tools.shared.lora_composition import (
    EvaluationCase,
    LoRACompositionApplication,
    MergeMethod,
)

app = LoRACompositionApplication("preferences.json")
adapters = app.load(["subject.safetensors", "style.safetensors"], {"subject": "subject", "style": "style"})
report = app.preflight(adapters, "sdxl/base", base_architecture="SDXL")
if report.compatible:
    conflicts = app.analyze(adapters)
    # Provide a backend evaluator that renders each fixed prompt/seed candidate.
```

The evaluator bridge and visual UI are intentionally separate from numerical merging: this package does not silently render images, infer rights, or claim that a generic weighted merge reproduces the research-specific ZipLoRA or K-LoRA training pipelines. `top_k` and `zip_style` are transparent training-free baselines. Dense analysis is limited to 8,388,608 elements (32 MiB per float32 update); start with representative adapters and a small candidate grid.
