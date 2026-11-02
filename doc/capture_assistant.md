# Touka Capture Assistant

Capture Assistant imports a local folder into a `CaptureSet`, keeps source-file hashes and selected capture metadata, reports blur/clipping proxies, and exposes optional exposure fusion and backend routing. It does not require a camera or polarizer. No network operation occurs; generated manifests default to `local_only`.

An optional `capture-set.json` provides structured metadata:

```json
{
  "schema": "capture-set.v1",
  "capture_set_id": "desk-scan-01",
  "aligned_frames_assumed": true,
  "frames": [
    {"path": "frame-01.png", "exposure_ev": -1, "iso": 100},
    {"path": "frame-02.png", "exposure_ev": 0, "iso": 100},
    {"path": "frame-03.dng", "exposure_ev": 1, "iso": 100, "polarization_angle": 45}
  ]
}
```

Without a manifest, image EXIF is read for capture time, exposure compensation, ISO, and aperture. Original image and RAW bytes remain unchanged and receive SHA-256 digests. Manifest paths must be file names within the selected folder. Imports are limited to 512 images/RAW files, 512 MiB total, and decoded images to 16 megapixels.

Distinct exposure values produce an approximate EV-normalized sRGB mean candidate. The fusion records its inputs and caveat; this is not calibrated linear-RAW HDR, does not estimate alignment, and can ghost moving content. Unequal image dimensions skip fusion. Blur and clipping metrics are explainable guidance proxies. A low-resolution inter-frame pixel-difference proxy can flag nearly identical captures; it does not estimate camera motion or viewpoint.

RAW/DNG bytes can be imported and preserved without optional dependencies. Processing needs an injected `RawFrameDecoder`; `RawpyFrameDecoder` uses `rawpy` lazily when that optional package is installed. Polarization metadata routes to the first injected `CaptureSetBackend` that declares support. Without a compatible backend, the ordinary weak-signal path remains available and records the fallback. A single image always works without special hardware.

The result manifest is returned to the caller as bytes; the application does not choose a save directory or upload capture data. `python -m unittest tests.test_capture_assistant` covers local import, path safety, quality guidance, exposure fusion, RAW adapter behavior, polarization routing, and single-image fallback.
