# Character Registry Tag Intake

[日本語](tag_intake.md)

## Current scope

`preview_character_intake` reads Tagger-style UTF-8 `.txt` captions next to images and returns review candidates grouped as `identity`, outfit-specific `outfit`, `context`, and `unclassified`. This is a preview: it does not register a Character Profile or start training. Unknown tags are not promoted to identity automatically, limiting the impact of misclassification.

The built-in taxonomy only proposes categories. A person must review and correct the candidates before Character registration.

## Input format

The dataset can be any explicitly supplied local directory. Put a UTF-8 `.txt` file with the same basename next to each image. Image extensions are matched case-insensitively. Exact filename stems take precedence, so files differing only by case are not cross-associated. Captions without a matching image remain in the preview with a warning. Captions under `outfits/<outfit_id>/` are grouped as outfit candidates. Other captions contribute to shared identity candidates or an unassigned outfit group. The unassigned group is marked with `is_unassigned=true`, so it cannot merge with a real profile named `unassigned`.

An optional `manifest.json` uses this shape:

```json
{
  "assets": [
    {
      "caption_file": "identity/ref-01.txt",
      "image_file": "identity/ref-01.png",
      "source_url": "https://source.example/item/123",
      "source_work_id": "123",
      "license_status": "verified status",
      "training_permission": "verified status"
    }
  ]
}
```

`caption_file` and `image_file` must be relative paths within the dataset. POSIX/Windows absolute paths, parent traversal, and manifest symlinks resolving outside the dataset are rejected. If the manifest or rights metadata is missing, the status stays `unknown`. Downloadability is not treated as permission to train on or redistribute an asset.

## Current limitations

- This feature does not choose a scraping source or download files. It is separate from source-specific APIs, terms, and license checks.
- Tag categories are suggestions. Manual correction UI and profile registration are follow-up work.
- It does not scan managed training materials or user data automatically. It reads only the dataset root explicitly supplied by its caller.
