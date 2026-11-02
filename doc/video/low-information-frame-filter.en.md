# Low-information video frame filter

[日本語](low-information-frame-filter.md)

`comfyui_support_tools.shared.video_frame_filter` analyzes normalized frames with inexpensive CPU features and returns a per-frame `FrameFilterReport` plus a `FrameFilterBatchManifest`. It is disabled by default. The scorer combines black/white ratios, luminance entropy, edge density, sharpness, optional OCR boxes, optional subject/saliency scores, and adjacent-frame evidence. It records `keep`, `drop`, `review`, or `error` with reasons and confidence. Decode failures remain separate from content-quality decisions.

`filter_existing_frame_folder` recursively analyzes image folders in deterministic order. Dry-run returns reports without writing. Apply leaves inputs unchanged, builds the full output tree in a temporary directory, validates it, then publishes the `kept/`, `rejected/`, `review/`, and `errors/` folders together with the JSON manifest. A failure removes the temporary output. `mark_only` writes only the manifest. It rejects overlapping input/output trees, symlinks, and attempts to overwrite existing outputs.

The Movie Frames UI exposes a disabled-by-default filter checkbox, conservative/balanced/aggressive/custom presets, per-rule toggles, an action, a title/credits policy, and the main custom thresholds. Settings are stored with presets. `preview only` is enabled by default so the first run shows counts; after selecting apply, filtering keeps the current Movie Frames output intact and copies results to a sibling `<video>_filtered` folder. A separate button handles existing frame folders. Apply is non-destructive and does not overwrite existing files.

Text detection uses a local Tesseract adapter that supplies `FrameTextBox` values. When filtering is enabled with text-only or title/credits rules, the Tesseract executable and language data are required. `auto` selects `jpn+eng` when both language packs are available and otherwise selects `eng`. If Tesseract is unavailable, disable the OCR rules or install Tesseract. Raw OCR text is not written to the manifest; the engine version is recorded as provenance. Subject/saliency scores remain optional. The filter does not run VLM. The current UI reads images already emitted by FFmpeg. An analyze-before-final-encode path requires connecting a decoder adapter that passes normalized frames directly to the shared analysis API.

## Example

```python
from pathlib import Path

from comfyui_support_tools.shared.contracts.frame_filter import FrameFilterOptions
from comfyui_support_tools.shared.frame_filter_application import filter_existing_frame_folder
from comfyui_support_tools.shared.tesseract_text_detector import TesseractTextDetector

options = FrameFilterOptions(enabled=True)
preview = filter_existing_frame_folder(
    Path("frames"), Path("filtered"), options, text_detector=TesseractTextDetector()
)
print(preview.kept_count, preview.dropped_count, preview.review_count)
```

`FrameFilterOptions` controls global enablement and individual black/white/transition/text-only/title-credits/low-detail/blur/neighbor switches. Presets keep low-confidence candidates in review to avoid deleting useful frames. `custom` exposes extreme-ratio, candidate-score, title-score, and structure-protection thresholds. Title and credits handling can be `keep`, `drop`, or `separate`; `separate` copies frames to a separate bucket and retains their originals.

## Validation and limits

Synthetic fixtures cover pure black/white, dark texture, a subject on a white background, normal footage with subtitles, OCR-assisted text-only scenes, title policy, dark transitions between meaningful scenes, decode errors, dry-run, separate-folder copying, cleanup after apply failure, mark-only, and source preservation. These fixtures are not a benchmark of false-drop rates on real videos. Fade/blur use limited neighbor heuristics, and near-duplicate similarity is reported but never automatically dropped. Dedicated persistent-subtitle-overlay handling, adaptive per-video calibration, an interactive review GUI, real-data benchmarks, and digest-application integration remain unimplemented. Review the dry-run and sample images before applying, and validate the aggressive preset against a representative dataset.
