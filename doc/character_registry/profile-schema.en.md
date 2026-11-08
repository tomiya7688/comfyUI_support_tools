# Character Registry Profile Schema

[日本語](profile_schema.md)

## Types added in this slice

- CharacterReferenceImage stores an ID derived from the content SHA-256 and the absolute path to the original image. Reference-only registration does not copy the image, and identical content receives the same ID. Its assignment is `unknown`, `mixed_custom`, or `outfit`; only the outfit case has an outfit ID. `selected_for_training` records the user's explicit training-candidate choice and defaults to `false`.
- `CharacterProfile` stores an opaque stable `character_id`, identity candidates, confirmed/rejected traits, outfit profiles, reference image IDs, source provenance, and UTC timestamps.
- `CharacterOutfitProfile` stores outerwear, garments, accessories, innerwear, visibility rules, manually assigned image IDs, confidence, and manual confirmation state.
- `create_character_id()` creates a random opaque ID once. Do not regenerate an existing ID when its display name changes.

Both types are immutable dataclasses. They reject blank display names, invalid IDs, duplicate outfit IDs, missing default outfit references, and naive timestamps. Confidence must be a finite value from 0.0 through 1.0.

Older JSON without image-assignment fields loads with `unknown` assignment; missing `selected_for_training` loads as `false`. A profile validates that each assigned outfit exists and that its image ID appears in that outfit's `source_image_ids`.

## Storage format

`CharacterProfileStore` accepts only an explicit storage root from its caller and atomically saves/loads schema version 1 JSON as `<character_id>.json`. It has no default storage path and does not search user data. The caller passes the path chosen from application settings. Unknown versions, malformed field types, paths outside the root, and profile-file symlinks are rejected.

## Current boundary

The profile contracts, JSON save/load, reference-only image registration, and per-image training-candidate selection are available. The selection is persisted but is not yet connected to a trainer or training handoff. Image copying/compression, automatic image analysis, editing saved profiles through a Character Library UI, and prompt injection are also not implemented here. Suggested tags are not automatically promoted to confirmed traits; the caller must make confirmation explicit.
