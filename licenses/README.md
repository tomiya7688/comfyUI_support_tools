# License file layout

Store third-party license texts here only after verifying the exact component
and version used by a distribution. Preserve the original license text and
record its component, version, source, and whether it is bundled, downloaded,
or user-provided in `THIRD_PARTY_NOTICES.md` and the machine-readable manifest.

Do not infer a complete artifact inventory from top-level Python package names:
wheels may contain separately licensed native libraries. Until the PyInstaller
inventory is implemented and verified, this directory is intentionally not a
claim that every distribution dependency is covered.
