"""Collect the license texts for the exact runtime dependency closure in a build."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from importlib.metadata import Distribution, PackageNotFoundError, distribution, distributions
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


_LICENSE_PREFIXES = ("LICENSE", "NOTICE", "COPYING", "COPYRIGHT")
_NATIVE_SUFFIXES = {".dll", ".pyd", ".exe", ".so", ".dylib"}


def _native_artifact_inventory(distribution_dir: Path) -> list[dict]:
    """List and fingerprint native files actually present in the onedir output."""
    artifacts = []
    for path in sorted(distribution_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _NATIVE_SUFFIXES:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        artifacts.append({
            "path": path.relative_to(distribution_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "audit_status": "origin-and-license-unmapped",
        })
    return artifacts

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

def collect_license_inventory(root: Path, distribution_dir: Path) -> dict:
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
        "native_artifacts": _native_artifact_inventory(distribution_dir),
    }
    manifest_path = distribution_dir / "third_party_components.resolved.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
