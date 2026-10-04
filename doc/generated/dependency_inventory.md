# Python dependency inventory

Generated from the dependency manifests configured in tools/docs/config.json.
Repeated distributions are intentional when separate runtime environments need their own installation.

## requirements-kadoka-tools.txt — Application runtime (.venv)

Runtime dependencies for the GUI and its directly invoked application features.

| Distribution | Requirement | Purpose |
| --- | --- | --- |
| numpy | numpy==1.26.4 | Array operations used by Touka evaluation and image-processing features. |
| Pillow | Pillow==10.4.0 | Image loading, preview, conversion, and mask handling in application features. |
| opencv-python-headless | opencv-python-headless==4.10.0.84 | Touka frame/image processing without a bundled OpenCV GUI runtime. |
| requests | requests>=2.32,<3 | HTTP transport for ComfyUI, A1111, Tagger, and Ollama API clients. |
| psutil | psutil>=6,<8 | Optional process affinity and resource controls used by CPU-limiting features. |

## nuno/_touka/requirements.txt — Touka feature environment

Image and dataset processing dependencies installed separately from the GUI runtime.

| Distribution | Requirement | Purpose |
| --- | --- | --- |
| numpy | numpy==1.26.4 | Array and tensor preparation for image processing and dataset construction. |
| Pillow | Pillow==10.4.0 | Image, mask, and dataset file loading and saving. |
| opencv-python-headless | opencv-python-headless>=4.10 | Image and video-frame processing in Touka tools. |

## tools/build/requirements.txt — Build environment

Build-only dependencies; this manifest is not part of the application's runtime requirements.

| Distribution | Requirement | Purpose |
| --- | --- | --- |
| PyInstaller | PyInstaller>=6.0,<7 | Freezes the application into the Windows one-directory distribution. |
