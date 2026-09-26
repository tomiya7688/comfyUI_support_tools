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

Python-bundled OpenSSL, libffi, bzip2, and libmpdec are listed as separate native components.
OpenSSL, libffi, and bzip2 link to corresponding notices included in Python's `LICENSE.txt`. The
libffi 3.3.0 version is evidenced by the CPython 3.10.11 Windows build files;
the bzip2 1.0.8 pin is evidenced by its matching CPython Windows build files;
other CPython builds without an explicit pin remain version-unresolved. The
bundled liblzma 5.2.5 source is identified as public domain by XZ Utils;
because upstream notes toolchain contributions may affect binaries, the
compiled `_lzma.pyd` remains under binary-scope review. The Microsoft Visual
C++ Runtime is separately identified, but its redistribution terms remain
marked for review; the inventory does not assert that redistribution
rights have been established.

CPython 3.10.11 bundles libmpdec 2.5.1. Its BSD-2-Clause notice is copied
separately because the installed Python `LICENSE.txt` does not contain that
notice. The `_decimal.pyd` inventory entry links both the CPython wrapper
license and libmpdec license. Other Python builds remain version-unresolved
until individually verified.

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
