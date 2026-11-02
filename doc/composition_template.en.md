# Composition Template Extractor

[日本語](composition_template.md)

Launch the application with `python -m comfyui_support_tools.applications.composition_template`. Open an image and choose **Auto extract** to create resolution-independent 0..1 boxes for candidate subjects and negative space, a visual-attention grid, reading-flow points, and a coarse optional horizon. Drag on the canvas to add regions and edit their roles. Templates can be imported/exported as JSON. The user library lives at `~/.comfyui_support_tools/composition_templates`.

## Design and limitations

- `CompositionTemplate` stores only layout roles and geometric attention/depth/perspective cues. It excludes source pixels, color, clothing, identity, and artist/style attributes. Provenance stores the source SHA-256, source dimensions, algorithms, and warnings.
- Built-in extraction is a contrast/edge saliency proxy using Pillow and NumPy. It does not recognize people or object semantics, so candidate subject boxes are low-confidence approximations and should be reviewed. The source path and image are not stored.
- Pose, semantic subject detection, relative depth, and vanishing-point boundaries are injectable Protocol adapters. No model or weights are bundled; users must supply adapters for model-backed measurements. The default horizon estimate is also a coarse heuristic.
- FIT preserves geometry and adds letterboxed space; CROP removes portions outside the destination; SMART REFLOW shifts the main region slightly toward detected negative space. Smart reflow is a simple layout aid without semantic reasoning or complex polygon reflow. None of these policies stretches geometry.
- JSON is versioned and limited to 2 MiB; unknown fields, out-of-range coordinates, and duplicate region IDs are rejected. Library saves never overwrite an existing name.
- Guidance export is a generic JSON payload for downstream consumers. Direct integration with #348/#56/#82/#84/#354 and automatic ComfyUI workflow generation are not included.

Image processing requires the existing Pillow and NumPy dependencies. GUI launch requires Tk.
