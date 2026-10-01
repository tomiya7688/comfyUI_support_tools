# External applications

This directory holds separately maintained third-party applications and source
repositories used by this project. Their files and Git histories are not part of
this repository and are ignored by Git. Keep project-authored code in `scripts/`,
`src/`, `tools/`, and `tests/` instead.

Use `python tools/maintenance/move_external_apps.py` to preview the known local
application folders before moving them. The migration script does not move
models, checkpoints, wildcards, generated output, or user data. Existing
ComfyUI/WebUI model and output folders stay at their current locations; junctions
under the new application folders keep the backends working.
