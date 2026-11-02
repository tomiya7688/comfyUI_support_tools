# Weak-signal and layer-separation application

## Purpose

`shared.weak_signal` handles reflections, glare, paper show-through, veiling, weak detail, and uneven illumination through common observation, candidate, and evidence contracts. It supports manual modes and a provisional statistics-based mode suggestion, then exports candidate images and a JSON manifest for OCR or Inspector consumers.

```python
from comfyui_support_tools.shared.weak_signal import (
    ObservationInput, WeakSignalApplication, WeakSignalMode, WeakSignalRequest,
)

result = WeakSignalApplication().process(
    ObservationInput("scan-001", (encoded_png_bytes,)),
    WeakSignalRequest(mode=WeakSignalMode.PAPER_SHOWTHROUGH),
)
artifacts = WeakSignalApplication().export(result, output_dir)
```

`WeakSignalCandidate` carries images, named measurements, confidence, processor identity, and `OBSERVED` / `ENHANCED` / `INFERRED` / `COMPLETED` provenance. The exported `*.weak-signal.json` includes candidates, component images, provenance, and OCR candidate paths.

## Available backends

The built-in Pillow backend generates conservative candidates using local-background normalization, highlight suppression, contrast, and detail enhancement. Weak-detail mode returns conservative, natural, and enhanced alternatives. The original observation is preserved as an `observed_input` component.

Reflection processing accepts bursts or videos with at least three frames only when the caller declares them aligned. It computes a three-frame median and temporal residual. Residuals also contain scene motion and noise; they are not reflection masks. Reflection and transmission from a single image are underdetermined by the observation alone.

Touka's translucent-surface separation mode is unavailable by default until a compatible backend is registered. The existing Touka UI launches a standalone CLI application and is not connected to the common Python candidate contract. A `WeakSignalBackend` implementation can be injected into the registry to add Touka or ComfyUI integration without changing the UI.

## Input limits and constraints

Inputs are image bytes supported by Pillow, up to 16 megapixels and 512 frames. `video` means decoded frames; this contract does not decode video containers, align frames, or provide UI previews. Automatic mode is a brightness and histogram heuristic, not semantic recognition. Candidate ranking uses named structure-retention and contrast proxies, not an empirical image-quality evaluator.

## Validation

Run `python -m unittest tests.test_weak_signal` to validate contracts, candidate generation, alignment requirements, and provenance manifests.
