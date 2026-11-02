# Shared video frame analysis input

Video features should pass decoder output through
`DecodedVideoFrame` and `normalize_decoded_frame` before brightness filtering,
OCR, tagging, or VLM analysis. Decoder-specific options stay in the decoder
adapter; consumers receive `FrameAnalysisInput`.

`FrameAnalysisInput` retains dimensions, source pixel format, source primaries,
transfer, range and matrix tags, requested and actual time, PTS/time base,
stream metadata, and an explicit decode status. Valid frames expose read-only
linear sRGB/D65 pixels and a normalized 0..1 luminance plane. Packed RGB/BGR
8-bit and 16-bit layouts are supported. Decoders must convert planar YUV to a
packed RGB/BGR buffer using the source matrix and range before calling the
normalizer; unknown formats return `unsupported_pixel_format` without pixels.

BT.709, sRGB, PQ, and HLG transfer functions are supported. BT.709, BT.2020,
and Display P3 primaries convert to the same analysis gamut. HDR values use a
bounded Reinhard luminance map for analysis; this representation does not
replace source pixels for export or encoding. Unsupported tags or invalid
mastering metadata fail closed instead of silently changing thresholds.

`detect_active_picture` only accepts an explicit user rectangle or a matching
dark-edge rectangle found in multiple temporal samples. It retains the full
frame for uniformly dark scenes, inconsistent bars, invalid frames, and
single-frame input. Consumers apply the returned rectangle to their analysis
view; the source frame stays unchanged.

## Validation

`tests.test_video_frame_normalization` covers temporal letterbox detection,
dark-scene protection, user overrides, SDR/HDR luminance normalization,
limited-range 10-bit input, VFR PTS/time-base recovery, unsupported formats,
corrupt pixels, and decode/timestamp errors. Decoder adapters for both built-in
libav and FFmpeg CLI should construct the same `DecodedVideoFrame` contract;
this shared layer does not select or configure a decoder.
