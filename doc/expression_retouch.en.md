# Expression Retouch

[日本語](expression_retouch.md)

Launch with `python -m comfyui_support_tools.applications.expression_retouch`. OpenCV's frontal Haar cascade detects faces and supports selecting one face from a multi-face image. The editor provides automatic full-face/eyes/eyebrows/mouth/cheeks/tear masks, white-paint addition and right-drag black erasure on a canvas, expression presets and intensity, best-of-N generation, candidate comparison, and persisted edit metadata/history.

For ComfyUI, provide an API-format inpaint workflow. Set `EXPRESSION_RETOUCH_WORKFLOW=/absolute/path/workflow.json`, `EXPRESSION_RETOUCH_IMAGE_NODE`, and `EXPRESSION_RETOUCH_MASK_NODE` to the workflow's `LoadImage`/`LoadImageMask` node IDs. Positive/negative text nodes are inferred from titles where possible; set comma-separated `EXPRESSION_RETOUCH_PROMPT_NODES` and `EXPRESSION_RETOUCH_NEGATIVE_NODES` when needed. Sampler seed inputs are detected automatically. Set `EXPRESSION_RETOUCH_SAMPLER_NODE` to enable denoise control. `COMFYUI_API_URL` defaults to `http://127.0.0.1:8188`.

The adapter uploads the source and mask to ComfyUI; the workflow must use those inputs for masked inpainting/noise masking. The final image is composited with original pixels outside the mask, so non-target pixels remain unchanged. This does not guarantee that an image model preserves identity perfectly within the edited region.

## Evaluation and limitations

- Default face detection uses OpenCV's frontal Haar cascade. Facial parts are approximate ratios within each face box, not landmark segmentation. Profile faces, low resolution, and small faces reduce detection and region accuracy.
- No semantic expression-match classifier, face-embedding identity model, or visual artifact evaluator is bundled. Identity/non-target/locality values are image-difference proxies, not identity scores. A semantic evaluator can be injected; without one, candidates rank on preservation/locality proxies.
- Anime and photo modes plus a generic ComfyUI upload/inpaint adapter are available, subject to a compatible model/workflow/node mapping. Workflow Preset/Job Queue/#83/#84 integration, expression sheets, and a dedicated landmark model remain unconnected.
- History records source SHA-256, target/mode/regions/parameters/backend/seed/evaluations and immutable source, mask, and candidate PNG files.

Automated checks cover contracts, empty face detection, region masks, exact outside-mask preservation, candidate ranking/history, and ComfyUI source/mask upload mapping. Model quality still needs validation with the configured workflow and checkpoint.
