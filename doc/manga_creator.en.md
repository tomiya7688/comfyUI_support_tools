# Manga Creator / Storyboard

[日本語](manga_creator.md)

Launch with `python -m comfyui_support_tools.applications.manga_creator`. Turn a story or screenplay into an editable page/panel plan and maintain Character/Location/Prop Bibles, reading direction and page layout, per-panel prompt/pose/camera intent, dialogue/balloons, and continuity events in a resumable JSON project. Supported layout families are four-koma, manga page, vertical webtoon, and splash. The editor supports per-panel best-of-N candidate storage and selection, local panel regeneration, sequential rendering with saved progress, and page composition. Dialogue is composited onto a separate text layer after panel art.

The default `StoryboardRenderBackend` draws a rough composition sketch for review. It is not final artwork and does not call a trained image model. To connect ComfyUI, provide an API-format workflow JSON and set `COMFYUI_MANGA_WORKFLOW=/absolute/path/workflow.json` before launch. Optionally set `COMFYUI_API_URL=http://127.0.0.1:8188` for the local API endpoint. Select `comfyui` as the panel backend in the editor. Common CLIP text nodes are detected automatically; workflow-specific node IDs and sampler seed nodes can be configured through `ComfyUIPanelBackend`. Character/location/prop text is added to the prompt, but reference-image pixel conditioning is not injected into a generic workflow. Other generators can implement `PanelGenerationBackend` and be registered with Process. The story planner is a deterministic rule baseline: it recognizes `Name: dialogue` lines and distributes text across panels but does not understand narrative semantics, evaluate story beats, or guarantee cinematic direction.

## Storage and limits

- MangaProject schema v1 stores editable characters, locations, props, story sections, pages/panels, dialogue, render candidates, and continuity events as the project source of truth. PNG artifacts are kept in `panels/` and `pages/` beside the JSON document; project updates use atomic replacement.
- Project JSON is limited to 64 MiB, story text to 2 MiB, and panel images to 64 MiB/80 megapixels. Unknown fields, duplicate JSON keys, unknown bible references, out-of-range geometry, and malformed images are rejected.
- Dialogue and balloons remain separate from panel pixels and their exact strings remain in the project JSON. The compositor searches a configured font and common OS CJK font locations. Japanese glyphs cannot be rendered correctly in PNG previews if no suitable font is installed; that case returns a warning. Configure `generation_settings` with a `font_path` to choose a font.
- Candidate scoring uses only panel aspect, minimum resolution, and dialogue-density proxies. It does not measure character identity, pose/anatomy, OCR, story correspondence, or page reading flow. Candidate PNGs remain available after selection.
- Continuity memory applies explicit state events recorded from an accepted panel to later panels. It does not automatically recognize costume, prop, injury, or location changes.
- #348/#350/#353 router integration, Job Queue, Workflow Preset, external evaluation, a standard ComfyUI inpaint repair adapter, true vertical-glyph orientation, and PDF/CBZ/EPUB export are not connected. MangaFlow/DiffSensei/MangaCrafter inform adapter boundaries; their paper methods and weights are not included.

Tests cover four-koma panel planning, right-to-left order, speaker references, continuity timing, best-of-N persistence, single-panel regeneration, page composition, save/resume, and malformed JSON.
