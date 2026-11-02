# Face Style Retouch

Face Style Retouch provides a face-local contract for changing line, shading,
medium, era, and detail density while keeping identity, expression, pose, gaze,
hair, palette, and all pixels outside the edit mask under explicit controls.
The shared pipeline supports main, selected, grouped, and all-face selection;
bangs preservation; multiple backend candidates; preservation evaluation; and
fail-closed review when an evaluator or face locator is unavailable.

The repository does not bundle a face parser, identity/expression model, or
generative edit weights, and the main GUI does not expose a configured editing
backend yet. Hosts can inject these through `FaceRegionProvider`,
`FaceStyleBackend`, and `FaceStyleEvaluator`; without them the service returns a
review warning and does not claim a successful retouch. This keeps reference
images style-only at the API boundary and avoids claiming identity preservation
without an actual evaluator. Semantic Erase's generic region pipeline remains a
separate operation; expression edits should be explicitly chained through the
dedicated expression-retouch flow when available.
