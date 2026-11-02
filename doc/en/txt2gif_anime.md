# Txt2GIF Anime (Issue #347)

The shared short-loop processing lives in `shared.txt2gif`. `Txt2GifRequest` validates 4–15 fps, 8–48 frames, palette size, dithering, file budget, dimensions, and total pixel budget. Register a backend that generates a canonical still and extracts motion regions in `AnimationBackendRegistry`, then run it through `Txt2GifApplication.generate()`.

Key Art First anchors every frame to one canonical still. A backend returns each moving subject as an RGBA layer plus a clean plate with the original subject region inpainted. `render_key_art_loop()` keeps the plate static, periodically moves each layer, and makes the final frame pixel-identical to the first. The GIF encoder builds one shared palette across frames and applies dithering and infinite loop playback. If the output exceeds its byte budget, it reduces palette size and then resolution; if the minimum dimension still exceeds the limit, it fails without leaving a partial file.

Implemented today: backend protocol/registry, Key-Art motion renderer, loop closure, shared-palette GIF encoding, size budgeting, progress callback, and output diagnostics. Missing adapters: ComfyUI txt2img, AnimateDiff/ToonCrafter workflow execution, character segmentation, clean-plate inpainting, region-mask editor, desktop UI, and real-model quality evaluation. Until those adapters exist, the shared primitives do not provide a default executable prompt-to-GIF backend. The system also does not silently fall back to long-form video generation or narrative shots.

`tests.test_txt2gif` uses Pillow fixtures to verify region-only motion, frozen background, loop seam, shared palette/GIF timing, atomic size-budget failure, and backend orchestration.
