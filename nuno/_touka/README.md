# Image Enhancer

Small, general-purpose desktop utility for non-person imagery, making subtle information in ordinary imagery easier to inspect. It works by creating an adjustable processed copy and blending that copy over the original. It cannot recover information absent from the source.

## Run

```text
python -m pip install -r requirements.txt
python image_enhancer.py
```

On Windows, double-click `run_image_enhancer.bat`. On its first run it creates a local `.venv` beside the script and installs the pinned Pillow 10.4.0 and NumPy 1.26.4 versions. Later launches reuse that environment and verify the versions automatically.

Use **Open…**, shape the Master RGB or individual Red/Green/Blue curves, adjust contrast, highlights, shadows, and detail, then choose a blend mode and opacity. The preview is updated as controls move. **Show original** toggles between the source and processed preview. **Reset all** restores every curve and control to defaults. **Repeated passes** applies the same copy-and-blend operation up to five times. **Save export…** processes the full-resolution source image.

Click inside a curve editor to add a point, then drag points. The first and last points stay at the endpoints. Supported blend modes are Normal, Darken, Lighten, Multiply, Screen, and Overlay.

## Headless smoke check

```text
python image_enhancer.py --smoke-test
```

The source is never modified in place. Camera orientation metadata is applied when an image is opened. PNG export preserves alpha; JPEG export is handled by Pillow when the selected filename uses `.jpg` or `.jpeg`.
