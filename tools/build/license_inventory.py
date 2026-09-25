"""Collect the license texts for the exact runtime dependency closure in a build."""
from __future__ import annotations

import json
import os
import shutil
import sys
from importlib.metadata import Distribution, PackageNotFoundError, distribution, distributions
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
try:
    from .native_artifact_inventory import collect_native_artifact_inventory
except ImportError:  # Support direct script execution from tools/build.
    from native_artifact_inventory import collect_native_artifact_inventory


_LICENSE_PREFIXES = ("LICENSE", "NOTICE", "COPYING", "COPYRIGHT")
_CPYTHON_LIBFFI_PINS = {
    "3.10.11": {
        "version": "3.3.0",
        "source_url": "https://github.com/python/cpython/blob/v3.10.11/PCbuild/python.props",
        "source_script_url": "https://github.com/python/cpython/blob/v3.10.11/PCbuild/get_externals.bat",
    },
}
_EXTERNAL_COMPONENTS = (
    ("ComfyUI", "application"),
    ("WebUI1111", "application"),
    ("PixAI Tagger", "backend"),
    ("TagGUI", "application"),
    ("Ollama", "service"),
    ("FFmpeg", "binary"),
    ("7-Zip", "binary"),
    ("AI model weights", "model-weights"),
)


def _external_components() -> list[dict]:
    return [
        {
            "name": name,
            "component_type": component_type,
            "distribution_status": "external-only",
            "version": None,
            "license_metadata": None,
            "source_urls": [],
            "license_files": [],
            "audit_status": "not-audited-by-this-artifact",
            "note": "Version and license depend on the separately installed or user-provided copy; this artifact does not redistribute it.",
        }
        for name, component_type in _EXTERNAL_COMPONENTS
    ]


def _runtime_dependency_names(root: Path) -> list[str]:
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    available = {
        canonicalize_name(item.metadata["Name"]): item
        for item in distributions(path=[str(site_packages)])
        if item.metadata.get("Name")
    }
    requirements_file = root / "requirements-kadoka-tools.txt"
    pending = set()
    for raw_line in requirements_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line and not line.startswith(("-", ".")):
            pending.add(canonicalize_name(Requirement(line).name))

    resolved = {}
    while pending:
        name = pending.pop()
        if name in resolved:
            continue
        item = available.get(name)
        if item is None:
            raise RuntimeError(f"Runtime dependency is not installed: {name}")
        resolved[name] = item
        for raw_requirement in item.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is None or requirement.marker.evaluate():
                dependency = canonicalize_name(requirement.name)
                if dependency not in resolved:
                    pending.add(dependency)
    return [resolved[name] for name in sorted(resolved)]


def _license_files(item: Distribution, site_packages: Path) -> list[Path]:
    result = []
    for entry in item.files or ():
        relative = PurePosixPath(str(entry).replace("\\", "/"))
        if ".." in relative.parts or not relative.name.upper().startswith(_LICENSE_PREFIXES):
            continue
        source = Path(item.locate_file(entry))
        if source.is_file():
            result.append(source)
    if not result:
        raise RuntimeError(f"No license or notice files found for {item.metadata['Name']} {item.version}")
    return result


def _license_metadata(item: Distribution) -> dict:
    label = item.metadata.get("License", "")
    label = next((line.strip() for line in label.splitlines() if line.strip()), "")
    classifiers = [
        value.rsplit(" :: ", 1)[-1]
        for value in item.metadata.get_all("Classifier", [])
        if value.startswith("License ::")
    ]
    return {"metadata": label or None, "classifiers": classifiers}


def _copy_python_package_licenses(item: Distribution, site_packages: Path, target: Path) -> list[str]:
    package_name = canonicalize_name(item.metadata["Name"])
    copied = []
    for source in _license_files(item, site_packages):
        relative = source.relative_to(site_packages)
        destination = target / "licenses" / "python_packages" / package_name / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination.relative_to(target).as_posix())
    return copied


def _project_urls(item: Distribution) -> list[str]:
    return item.metadata.get_all("Project-URL", [])


def _pyinstaller_components(site_packages: Path, distribution_dir: Path) -> list[dict]:
    """Record PyInstaller code that is incorporated into the frozen executable."""
    try:
        pyinstaller = distribution("pyinstaller")
    except PackageNotFoundError as error:
        raise RuntimeError("PyInstaller is required to audit the onedir bootloader license") from error
    license_files = _copy_python_package_licenses(pyinstaller, site_packages, distribution_dir)
    project_urls = _project_urls(pyinstaller)
    common = {
        "distribution_status": "bundled-component",
        "version": pyinstaller.version,
        "source_urls": project_urls,
        "license_files": license_files,
    }
    return [
        {
            "name": "PyInstaller bootloader",
            "component_type": "executable-bootloader",
            "license_metadata": "GPL-2.0-or-later WITH Bootloader-exception",
            **common,
        },
        {
            "name": "PyInstaller runtime hooks",
            "component_type": "runtime-hooks",
            "license_metadata": "Apache-2.0",
            **common,
        },
    ]


def _python_native_components(
    distribution_dir: Path,
    python_license: str,
    python_version: str | None = None,
) -> list[dict]:
    """Describe separately identifiable native libraries shipped by Python."""
    names = {path.name.casefold() for path in distribution_dir.rglob("*") if path.is_file()}
    license_files = [python_license]
    components = []

    if any(name.startswith(("libcrypto-", "libssl-")) for name in names):
        import ssl

        fields = ssl.OPENSSL_VERSION.split()
        version = fields[1] if len(fields) > 1 and fields[0] == "OpenSSL" else None
        components.append({
            "name": "OpenSSL",
            "component_type": "native-runtime-library",
            "distribution_status": "bundled",
            "version": version,
            "license_metadata": "OpenSSL License AND Original SSLeay License",
            "source_urls": ["https://www.openssl.org/"],
            "license_files": license_files,
            **({"audit_status": "upstream-version-unresolved"} if version is None else {}),
        })

    if any(name.startswith("libffi-") and name.endswith(".dll") for name in names):
        pinned_build = _CPYTHON_LIBFFI_PINS.get(python_version or sys.version.split()[0])
        libffi = {
            "name": "libffi",
            "component_type": "native-runtime-library",
            "distribution_status": "bundled",
            "version": pinned_build["version"] if pinned_build else None,
            "license_metadata": "libffi license (included in Python LICENSE.txt)",
            "source_urls": ["https://github.com/libffi/libffi"],
            "license_files": license_files,
        }
        if pinned_build:
            libffi["version_source_urls"] = [pinned_build["source_url"], pinned_build["source_script_url"]]
        else:
            libffi["audit_status"] = "upstream-version-unresolved"
        components.append(libffi)

    if any(name.startswith(("vcruntime", "msvcp")) and name.endswith(".dll") for name in names):
        components.append({
            "name": "Microsoft Visual C++ Runtime",
            "component_type": "native-runtime-library",
            "distribution_status": "bundled",
            "version": None,
            "license_metadata": None,
            "source_urls": [
                "https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files"
            ],
            "license_files": [],
            "audit_status": "redistribution-terms-review-required",
        })

    return components


def collect_license_inventory(root: Path, distribution_dir: Path, build_toc: Path | None = None) -> dict:
    """Copy Python/Tcl and runtime package licenses and emit resolved metadata."""
    root = root.resolve()
    distribution_dir = distribution_dir.resolve()
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    components = []

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(f"Python runtime license is missing: {python_license}")
    python_target = distribution_dir / "licenses" / "Python" / "LICENSE.txt"
    python_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(python_license, python_target)
    components.append({
        "name": "Python",
        "distribution_status": "bundled",
        "version": sys.version.split()[0],
        "license_metadata": "Python Software Foundation License Agreement",
        "source_urls": ["https://www.python.org/"],
        "license_files": [python_target.relative_to(distribution_dir).as_posix()],
    })

    tcl_license = root / "licenses" / "TclTk" / "license.terms"
    if not tcl_license.is_file():
        raise RuntimeError(f"Tcl/Tk license terms are missing: {tcl_license}")
    tcl_target = distribution_dir / "licenses" / "TclTk" / "license.terms"
    tcl_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tcl_license, tcl_target)
    import tkinter
    components.append({
        "name": "Tcl/Tk",
        "distribution_status": "bundled",
        "version": f"Tcl {tkinter.TclVersion} / Tk {tkinter.TkVersion}",
        "license_metadata": "TCL",
        "source_urls": ["https://www.tcl-lang.org/"],
        "license_files": [tcl_target.relative_to(distribution_dir).as_posix()],
    })

    components.extend(
        _python_native_components(
            distribution_dir,
            python_target.relative_to(distribution_dir).as_posix(),
        )
    )
    components.extend(_pyinstaller_components(site_packages, distribution_dir))

    for item in _runtime_dependency_names(root):
        components.append({
            "name": item.metadata["Name"],
            "distribution_status": "bundled",
            "version": item.version,
            "license_metadata": _license_metadata(item),
            "source_urls": _project_urls(item),
            "license_files": _copy_python_package_licenses(item, site_packages, distribution_dir),
        })

    manifest = {
        "schema_version": 2,
        "distribution": "KadokaTools Windows onedir",
        "python_version": sys.version.split()[0],
        "components": components,
        "external_components": _external_components(),
        "native_artifacts": collect_native_artifact_inventory(
            distribution_dir,
            build_toc,
            components,
            site_packages,
            Path(sys.base_prefix),
            Path(os.environ["SystemRoot"]) if os.environ.get("SystemRoot") else None,
        ),
    }
    manifest_path = distribution_dir / "third_party_components.resolved.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
