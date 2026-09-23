# License file layout

The build collector stores the Tcl/Tk terms here as source input. Runtime
Python wheel license and notice files are copied unmodified into the onedir
artifact under `licenses/python_packages/<normalized-name>/`.

Do not infer a complete system inventory from Python package metadata alone.
The collector covers the active Python dependency closure and Python/Tcl/Tk
runtime, but OS-provided libraries and separately installed backends remain
outside this inventory.
