# License file layout

The build collector stores the Tcl/Tk terms here as source input. Runtime
Python wheel license and notice files are copied unmodified into the onedir
artifact under `licenses/python_packages/<normalized-name>/`.

Do not infer a complete system inventory from Python package metadata alone.
The collector covers the active Python dependency closure and Python/Tcl/Tk
runtime, but OS-provided libraries and separately installed backends remain
outside this inventory.

The resolved manifest marks artifact contents as `bundled` and separately lists
external-only applications, services, binaries, and model weights. External
items have no asserted version or license metadata: those depend on the user's
separate installation and require an exact-version audit before redistribution.

The onedir also embeds PyInstaller bootloader and runtime-hook code. Their separately identified license grants (GPL with the bootloader exception, and Apache-2.0 for runtime hooks) and source version are listed in the resolved manifest; the PyInstaller COPYING.txt is copied into the artifact.

The `native_artifacts` manifest section fingerprints each `.dll`, `.pyd`, `.exe`, `.so`, and `.dylib` found in the onedir output. A fingerprint is an exact-file identity. The manifest attempts to associate each file with its PyInstaller build source and package license documents, while sanitizing absolute builder paths. Unresolved and operating-system-supplied items still require license review.

OpenSSL, libffi, and bzip2 components shipped with Python are attributed
separately, not treated as Python-owned code. Their versions are sourced from
the matching CPython Windows build metadata where known. The Microsoft
Visual C++ Runtime is also attributed separately and remains pending review of
the applicable redistribution terms.

The `_lzma.pyd` artifact is linked to XZ Utils liblzma 5.2.5. Upstream's
`COPYING` identifies the liblzma source as public domain and cautions that
toolchain contributions can affect the compiled binary; therefore, the
artifact's binary license scope remains marked for review.

The bundled `_decimal.pyd` includes CPython's extension wrapper and libmpdec.
For the audited CPython 3.10.11 runtime, libmpdec is version 2.5.1 and its
BSD-2-Clause notice is stored in `licenses/libmpdec/LICENSE.txt` and copied
into the onedir artifact. The inventory links both the Python and libmpdec
license documents; other Python builds remain unresolved until individually
verified.

The bundled `pyexpat.pyd` contains CPython's extension wrapper and Expat.
For the audited CPython 3.10.11 runtime, Expat is version 2.5.0 and its MIT
notice is stored in `licenses/expat/LICENSE.txt` and copied into the onedir
artifact. The inventory links both the Python and Expat license documents;
other Python builds remain unresolved until individually verified.

The bundled `_ssl.pyd` contains CPython's extension wrapper and uses OpenSSL.
For the audited CPython 3.10.11 runtime, OpenSSL is version 1.1.1t and its
OpenSSL plus Original SSLeay notices are included in the copied Python
`LICENSE.txt`. The inventory links the Python license document and pinned
CPython source/build metadata; other Python/OpenSSL builds remain unresolved
until individually verified.
The bundled _asyncio.pyd is linked to the Python runtime component and its
LICENSE.txt document in the native artifact manifest. CPython 3.10.11's
upstream implementation source is Modules/_asynciomodule.c; unverified Python
builds retain their detected runtime version rather than this exact pin.

The bundled `_overlapped.pyd` is the CPython 3.10.11 Windows overlapped-I/O
extension. Its artifact inventory entry links the copied Python
`LICENSE.txt`, upstream implementation, and Windows build project. Other
Python runtime versions remain under review until individually verified.
