# Touka Capture Assistant

Capture Assistant imports a local folder into a `CaptureSet`, preserves source-file hashes and selected capture metadata, reports blur/clipping proxies, and provides optional exposure fusion and backend routing. It does not require a camera or polarizer. It performs no network operations; result manifests default to `local_only`.

An optional `capture-set.json` supplies structured metadata:

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

Without a manifest, image EXIF is read for capture time, exposure compensation, ISO, and aperture. Original image and RAW bytes remain unchanged and receive SHA-256 digests. Manifest paths must be file names inside the selected folder. Imports are limited to 512 files and 512 MiB total; decoded images are limited to 16 megapixels.

Distinct exposure values produce an approximate EV-normalized sRGB mean candidate. Fusion records its inputs and caveat; it is not calibrated linear-RAW HDR, does not estimate alignment, and can ghost moving subjects. Unequal frame dimensions skip fusion. Blur and clipping are explainable guidance proxies. A low-resolution inter-frame pixel-difference proxy can flag nearly identical captures; it does not estimate camera motion or viewpoint.

RAW/DNG bytes can be imported and preserved without optional dependencies. Processing requires an injected `RawFrameDecoder`; `RawpyFrameDecoder` lazily uses `rawpy` when that optional package is installed. Polarization metadata routes to the first injected `CaptureSetBackend` that declares support. Without a compatible backend, the ordinary weak-signal path remains available and records the fallback. A single image works without special hardware.

The result manifest is returned as bytes; the application leaves the save directory to its caller and never uploads capture data. Run `python -m unittest tests.test_capture_assistant` to cover local import, path safety, quality guidance, exposure fusion, RAW adapter behavior, polarization routing, and single-image fallback.
