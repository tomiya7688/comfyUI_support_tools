# Character Registry intake screen

[日本語](../../character_registry/ui.md)

The **Character Registry** tab in the existing Tabbed Tools app reads a caption dataset, optionally adds Civitai LoRA metadata, lets you review and manually classify tag candidates, and registers the confirmed result as a Character profile.

1. Choose the caption dataset folder and profile storage folder. The selected paths are stored under the configured `USER_INPUT_DIR/config/common/character_registry.json` (by default, `user_data/input/config/common/character_registry.json`).
2. Enter a stable ID, display name, and optional aliases.
3. Optionally search Civitai and select a LoRA version. The tool does not download model weights or images.
4. Review the preview and manually move selected tags into `identity`, `outfit`, or `innerwear`. Suggestions are never registered automatically. Innerwear is omitted from regular prompts. You can add custom tags when needed.
5. Optionally select local files under **Character reference images**. The app does not copy or analyze them; it stores their absolute paths and content SHA-256 IDs. Identical content is deduplicated. If a file is moved, remove the old reference and select the moved file again.
6. Confirm the identity tags, then classify tags for each outfit and press **Add this outfit**. You can add several outfits in sequence and remove an accidentally added outfit from the list. The first outfit becomes the initial default; choose a different one from **Default outfit** before registering if needed. Any outfit still being edited is also included when registering. The app then writes the character wildcard bundle and LoRA wrapper to the configured wildcard root.

Reference images currently belong to the Character as a whole. Per-outfit assignment, Tagger analysis, managed copies, thumbnails, and quality/duplicate analysis are not implemented yet.

`character_with_lora/<character_id>.txt` references both `__anime_character_lora/<character_id>__` and `__anime_character/<character_id>__`. After registration, use the **Character LoRA choices** editor to create `anime_character_lora/<character_id>.txt`. Enter one `<lora:local_model_name:strength>` call per line; relative weights such as `@weight=3::<lora:model_a:0.8>` are supported. The destination comes from the shared `wildcards` setting (`WILDCARDS_DIR`). If writing fails, the profile remains saved and the screen lets you retry wildcard export.

Civitai candidates can be loaded page by page. If the ID, display name, aliases, dataset, or selected LoRA changes after preview, create a new preview before registration. Paths used by preview and registration are saved to settings.

Civitai usage terms and training permissions are not automatically approved. Review the recorded provenance and permissions before using registered data.
