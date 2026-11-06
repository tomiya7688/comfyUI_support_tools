# Character Registry intake screen

[日本語](../../character_registry/ui.md)

The **Character Registry** tab in the existing Tabbed Tools app reads a caption dataset, optionally adds Civitai LoRA metadata, lets you review and manually classify tag candidates, and registers the confirmed result as a Character profile.

1. Choose the caption dataset folder and profile storage folder. The selected paths are stored under the configured `USER_INPUT_DIR/config/common/character_registry.json` (by default, `user_data/input/config/common/character_registry.json`).
2. Enter a stable ID, display name, and optional aliases.
3. Optionally search Civitai and select a LoRA version. The tool does not download model weights or images.
4. Review the preview and manually move selected tags into `identity` or `outfit`. Suggestions are never registered automatically. You can add custom tags when needed.
5. Confirm at least one identity tag, optionally provide an outfit ID/name, and register. The app then writes the character wildcard bundle and LoRA wrapper to the configured wildcard root.

`character_with_lora/<character_id>.txt` references both `__character_lora/<character_id>__` and `__anime_character/<character_id>__`. The destination comes from the shared `wildcards` setting (`WILDCARDS_DIR`). If writing fails, the screen reports that the profile was saved and shows the export error.

Civitai usage terms and training permissions are not automatically approved. Review the recorded provenance and permissions before using registered data.
