# Exporting wildcard bundles from Character Registry

[日本語](wildcard-export.md)

`build_character_wildcard_files(profile)` converts a confirmed CharacterProfile into root-relative paths and UTF-8 contents for a wildcard root. It does not create files; the caller chooses the destination from application settings.

The output uses the stable `character_id` and separates these roles:

- `anime_character/<id>/identity.txt`: only `confirmed_core_traits`
- `anime_character/<id>/outfit/<outfit_id>.txt`: outerwear, garment, and accessory traits for manually confirmed outfits
- `anime_character/<id>.txt`: references identity and the confirmed default outfit
- `character_with_lora/<id>.txt`: references `anime_character_lora/<id>` and the character wildcard

Unconfirmed identity candidates and outfits are omitted. Innerwear traits and visibility rules are not injected into regular prompts. Export raises `ValueError` when there are no confirmed identity traits. Traits containing wildcard/inline-choice syntax or line breaks are also rejected.

Create `anime_character_lora/<id>.txt` in the Character Registry's **Character LoRA choices** editor after registering the profile. Enter a local LoRA name and strength as `<lora:model_name:0.8>`. Add one candidate per line; relative weights such as `@weight=3::<lora:model_a:0.8>` are supported. Saving validates each wildcard weight and LoRA-call syntax and requires at least one positive-weight choice. The tool does not download model weights or Civitai images.

The saved file is referenced by the existing wrapper. Wildcard caching reuses the selected choice within one prompt and throughout one sequential generation run. Before generation, verify that each referenced LoRA exists locally and is compatible with the active base model.
