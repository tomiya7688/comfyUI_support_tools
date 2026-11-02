# Character Registry

[日本語](character-registry.md)

`comfyui_support_tools.applications.character_registry` stores character assets under stable `character_id` values, separating identity, outfits, reference images, and prompt policy. The GUI exposes a Character Library for registration, renaming, aliases, outfit profiles, adding/editing/rejecting identity and outfit traits, image registration, and a resolved prompt preview.

Core identity traits remain separate from outfit traits. A custom outfit suppresses only registered traits in the same category. Hidden traits are omitted by default and are included only when camera, pose, material, or explicit user evidence makes visibility likely. Each visibility decision includes evidence reasons and confidence.

Profiles are atomically stored as JSON. Updates use the loaded content hash as an optimistic concurrency token. Renaming preserves the stable ID. Image registration records the original hash for exact duplicate detection and supports reference-only, managed WebP, and Original + WebP storage. Training source selection prefers the original and returns a warning when only compressed content is available.

Dataset readiness reports selected/effective image counts, exact duplicate ratio, average quality, outfit count, and a low-shot strategy suggestion. Image count alone never blocks training.

## Current boundaries

The Character Library is connected to the current Tk application. Automatic trait classification, outfit-cluster suggestions, Media Browser “Add to Character”, generated-image import, one-click training adapter handoff, actual integration with existing #55/#274/#277/#278/#282/#356/#357 workflows, model-family-specific verbosity, and shared structured prompt conflict categories are not connected yet. Readiness metrics are initial heuristics, not calibrated evidence of training success. These remaining requirements are not claimed as complete.
