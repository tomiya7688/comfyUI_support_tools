# Tool / Settings Registry

[日本語](tool-registry.md)

`scripts/tool_registry.py` is the source of truth for each legacy tool's stable ID, label, category, settings ID, implementation binding, media/action metadata, and migration state. The UI shell loads implementations lazily in descriptor order. `scripts.tab_catalog.TAB_CATALOG` and `STABLE_SETTINGS_IDS` derive from the same descriptors. Class names remain migration-only metadata for legacy settings; they are not stable tool identities.

`ToolRegistry` rejects duplicate IDs, settings IDs, and legacy class adapters at registration. It preserves existing tab order and resolves the `{backend}` label template in the shell. Adding a legacy tab requires one descriptor and implementation binding, without repeating its registration in the app, catalog, and settings map. New Applications do not need to register in this legacy registry.

Validation covers a fake extension binding, duplicate rejection, legacy order, and the settings migration adapter.
