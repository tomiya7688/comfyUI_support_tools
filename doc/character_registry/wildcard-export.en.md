# Exporting wildcard bundles from Character Registry

[日本語](wildcard-export.md)

`build_character_wildcard_files(profile)` converts a confirmed CharacterProfile into root-relative paths and UTF-8 contents for a wildcard root. It does not create files; the caller chooses the destination from application settings.

The output uses the stable `character_id` and separates these roles:

- `anime_character/<id>/identity.txt`: only `confirmed_core_traits`
- `anime_character/<id>/outfit/<outfit_id>.txt`: outerwear, garment, and accessory traits for manually confirmed outfits
- `anime_character/<id>.txt`: references identity and the confirmed default outfit
- `character_with_lora/<id>.txt`: references `anime_character_lora/<id>` and the character wildcard

Unconfirmed identity candidates and outfits are omitted. Innerwear traits and visibility rules are not injected into regular prompts. Export raises `ValueError` when there are no confirmed identity traits. Traits containing wildcard/inline-choice syntax or line breaks are also rejected.

This exporter does not create `anime_character_lora/<id>.txt`. The LoRA registration flow owns that LoRA-call wildcard; the wrapper only references it. The UI reports when the mapping is missing.
