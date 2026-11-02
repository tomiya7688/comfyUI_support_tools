# Pixel Sprite Animation and Sheet Creator

`shared.pixel_sprite` defines a canonical-anchor sequence contract and an
injectable frame generator. A single source sprite supplies the silhouette and
canonical palette. The pipeline generates selected 1/4/8-direction action
frames, applies nearest-neighbor fit into fixed cells, reuses one palette,
orders frames by direction/action/index, packs a strict grid, and exports
individual PNGs, sprite-sheet PNG, animation JSON, and optional looping GIF or
lossless WebP. Layout metadata records the exact cell rectangles and frame
pose instructions. The `repack` API accepts externally edited frame images and
applies the same grid and canonical palette before exporting again.

Generation and identity evaluation are host adapters; no diffusion model,
pose-control workflow, or character-identity embedding is bundled. Without an
evaluator, output is marked for manual review and the service does not claim
identity consistency. Frame generation can still be exercised through a host
provider. A built-in img2img adapter can draft frames through the configured
A1111/ComfyUI backend, with the canonical sprite and action/direction prompt as
conditioning; this does not guarantee identity or pose correctness. Export
uses a staged directory and refuses to overwrite existing assets.
