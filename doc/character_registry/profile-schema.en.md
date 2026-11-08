# Character Registry Profile Schema

[日本語](profile_schema.md)

## Types added in this slice

- CharacterReferenceImage stores an ID derived from the content SHA-256 and the absolute path to the original image. Reference-only registration does not copy the image, and identical content receives the same ID.
- `CharacterProfile` stores an opaque stable `character_id`, identity candidates, confirmed/rejected traits, outfit profiles, reference image IDs, source provenance, and UTC timestamps.
- `CharacterOutfitProfile` stores outerwear, garments, accessories, innerwear, visibility rules, image references, confidence, and manual confirmation state.
- `create_character_id()` creates a random opaque ID once. Do not regenerate an existing ID when its display name changes.

Both types are immutable dataclasses. They reject blank display names, invalid IDs, duplicate outfit IDs, missing default outfit references, and naive timestamps. Confidence must be a finite value from 0.0 through 1.0.

## Storage format

`CharacterProfileStore` accepts only an explicit storage root from its caller and atomically saves/loads schema version 1 JSON as `<character_id>.json`. It has no default storage path and does not search user data. The caller passes the path chosen from application settings. Unknown versions, malformed field types, paths outside the root, and profile-file symlinks are rejected.

## Current boundary

The profile contracts, JSON save/load, and reference-only registration of selected images are available. Image copying/compression, automatic image analysis, editing saved profiles through a Character Library UI, prompt injection, and training are not implemented here. Suggested tags are not automatically promoted to confirmed traits; the caller must make confirmation explicit.
