# Third-Party Notices

The project-owned code is licensed under the MIT License in `LICENSE`. This
does not relicense bundled third-party libraries, binaries, or model weights.

The Windows onedir build copies the Python runtime and Tcl/Tk license terms,
plus license/notice files from the active dependency closure resolved from
`requirements-kadoka-tools.txt`. It writes
`third_party_components.resolved.json` beside the executable with exact
versions, upstream license metadata, source URLs, and copied notice paths.
Wheel-provided notices are retained verbatim, including nested native
components reported by upstream distributions.

The build configuration excludes PyTorch, torchvision, and torchaudio.
ComfyUI, WebUI1111, PixAI Tagger, TagGUI, Ollama, FFmpeg, 7-Zip, and AI model weights
are external/user-provided and are not bundled in the standard onedir artifact.
The generated `external_components` section records these items as not bundled.
Their installed versions and licenses vary by user, so this project does not make
license or redistribution claims for them here. Audit each exact upstream
component before adding it to a distributable artifact.
