# Semantic Erase Retouch

Semantic Erase is available from the Inspector for one selected image. The dialog
keeps the source read-only, lets the user paint and erase a mask, runs a candidate
through the pluggable processing service, shows preservation/boundary/residual
scores, and only copies a reviewed PNG to a user-selected path. Candidate files and
versioned operation history live in `.semantic-erase-history`; Undo and Redo move
the active history pointer without deleting source or candidate files.

The shared service accepts text queries, optional normalized range constraints,
manual masks, selected-match policies, fill policies, quality budgets, and batch
requests. Multiple region providers are merged and deduplicated. `remove_all`
unions every selected mask, `selected` and `all_except_selected` require an exact
match ID, and `inside_range` requires a range. Mask dilation variants are tried
within the requested candidate budget. A residual-target check runs against the
same registered region providers after inpainting; residual matches trigger local
mask expansion and retry. Candidate ranking includes target absence, exact
outside-mask preservation, and a local boundary gradient score.

Region detectors and inpaint models are extension points. A host can adapt
GroundingDINO (or another text grounding detector) and SAM 2 (or another promptable
segmenter) to `TextGroundingDetector` and `MaskSegmenter`, then register a
`GroundedSegmentationProvider`. Attribute/state models such as VLMs, taggers, face
parsers, and human parsers can implement `AttributeStateFallbackProvider`. Host
backends such as LaMa/MAT, BrushNet, PowerPaint, diffusion inpaint, and Qwen/FLUX
can be wrapped by `CallableInpaintBackend` and registered by stable ID. Registries
are deterministic and the OpenCV Telea backend remains the safe local fallback.

This repository does **not** bundle or download GroundingDINO, SAM 2, LaMa/MAT,
BrushNet, PowerPaint, diffusion models, or their weights. The current desktop UI
provides manual-mask editing with OpenCV Telea. Semantic text detection and
semantic skin/cloth restoration become available only after a host registers
model adapters. Without a registered detector, a text-only request fails closed;
without a detector to recheck the result, the candidate stays in review and is
never marked automatically accepted. The CPU baseline warns when asked to follow
skin, clothing, or custom-prompt fill instructions because it performs local
texture interpolation only.

Model integrations must be tested against the user's representative images before
they are used for automatic batch cleanup. Preservation and boundary scores are
technical heuristics, not identity recognition or a guarantee that a retouch is
visually correct. All final outputs are copies; this feature never overwrites the
input.
