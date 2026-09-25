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
The frozen executable also contains the PyInstaller bootloader (GPL-2.0-or-later
with Bootloader exception) and PyInstaller runtime hooks (Apache-2.0). Their
resolved versions and license text are included in the onedir manifest and
license directory.
The generated manifest fingerprints every native executable, DLL, and Python
extension and uses PyInstaller's COLLECT table to link source paths to package,
Python-runtime, Windows-system, or external-build origins when possible. Local
absolute source paths are never written into the artifact; unresolved origins
remain explicitly marked for review. A fingerprint or origin label is not by
itself a license-compliance determination.

Python-bundled OpenSSL and libffi are listed as separate native components and
linked to the corresponding notices included in Python's `LICENSE.txt`. The
Microsoft Visual C++ Runtime is separately identified, but its redistribution
terms remain marked for review; the inventory does not assert that redistribution
rights have been established.

Python extension file present in the onedir output. These paths are an audit
inventory only: entries whose origin/license is not mapped remain explicitly
unresolved and are not represented as license-cleared.

The build configuration excludes PyTorch, torchvision, and torchaudio.
ComfyUI, WebUI1111, PixAI Tagger, TagGUI, Ollama, FFmpeg, 7-Zip, and AI model weights
are external/user-provided and are not bundled in the standard onedir artifact.
The generated `external_components` section records these items as not bundled.
Their installed versions and licenses vary by user, so this project does not make
license or redistribution claims for them here. Audit each exact upstream
component before adding it to a distributable artifact.
