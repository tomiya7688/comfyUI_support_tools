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
