"""Attribute onedir native files to PyInstaller build sources without leaking absolute paths."""
from __future__ import annotations

import ast
import hashlib
import os
from importlib.metadata import distributions
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name

_SUFFIXES = {".dll", ".pyd", ".exe", ".so", ".dylib"}


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve())).casefold()


def _within(path: Path, root: Path | None) -> bool:
    if root is None:
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _load_sources(toc_path: Path | None) -> dict[str, tuple[Path, str]]:
    if toc_path is None or not toc_path.is_file():
        return {}
    try:
        entries = ast.literal_eval(toc_path.read_text(encoding="utf-8"))[0]
    except (OSError, SyntaxError, ValueError, TypeError, IndexError) as error:
        raise RuntimeError("Unable to parse PyInstaller COLLECT table") from error
    return {
        str(item[0]).replace("\\", "/").casefold(): (Path(item[1]), str(item[2]))
        for item in entries
        if isinstance(item, tuple)
        and len(item) >= 3
        and PurePosixPath(str(item[0]).replace("\\", "/")).suffix.lower() in _SUFFIXES
    }


def _package_owners(site_packages: Path) -> dict[str, dict]:
    owners = {}
    for item in distributions(path=[str(site_packages)]):
        name = item.metadata.get("Name")
        if not name:
            continue
        for entry in item.files or ():
            if PurePosixPath(str(entry).replace("\\", "/")).suffix.lower() not in _SUFFIXES:
                continue
            source = Path(item.locate_file(entry))
            if source.is_file():
                owners.setdefault(_key(source), {"name": name, "version": item.version})
    return owners


def _license_component(name: str, components: list[dict]) -> dict | None:
    canonical = canonicalize_name(name)
    return next(
        (item for item in components if canonicalize_name(item.get("name", "")) == canonical),
        None,
    )


def _source_hint(source: Path) -> str:
    parts = [
        part for part in source.parent.parts
        if part.casefold() not in {"users", "tomiy", ".cache", "codex-runtimes", "dependencies"}
    ]
    return "/".join(parts[-3:])


def _attribute(
    source: Path,
    typecode: str,
    owners: dict[str, dict],
    components: list[dict],
    site_packages: Path,
    python_root: Path,
    system_root: Path | None,
) -> dict:
    if typecode == "EXECUTABLE":
        name = "PyInstaller bootloader"
        item = next((component for component in components if component["name"] == name), {})
        return {
            "origin_type": "build-tool-component",
            "origin_component": name,
            "origin_version": item.get("version"),
            "license_files": item.get("license_files", []),
            "audit_status": "origin-and-license-document-linked",
        }

    owner = owners.get(_key(source))
    if owner:
        name = owner["name"]
        origin_type = "python-package"
        if canonicalize_name(name) == "pyinstaller":
            parts = {part.casefold() for part in source.parts}
            name = "PyInstaller bootloader" if "bootloader" in parts else "PyInstaller runtime hooks"
            origin_type = "build-tool-component"
        item = _license_component(name, components)
        licenses = item.get("license_files", []) if item else []
        return {
            "origin_type": origin_type,
            "origin_component": name,
            "origin_version": owner["version"],
            "license_files": licenses,
            "audit_status": "origin-and-license-document-linked" if licenses else "license-document-not-linked",
        }

    filename = source.name.casefold()
    runtime_component_name = None
    if filename.startswith(("libcrypto-", "libssl-")):
        runtime_component_name = "OpenSSL"
    elif filename == "_bz2.pyd":
        runtime_component_name = "bzip2"
    elif filename.startswith("libffi-") and filename.endswith(".dll"):
        runtime_component_name = "libffi"
    elif filename.startswith(("vcruntime", "msvcp")) and filename.endswith(".dll"):
        runtime_component_name = "Microsoft Visual C++ Runtime"
    if runtime_component_name:
        item = _license_component(runtime_component_name, components)
        if item:
            return {
                "origin_type": "native-runtime-library",
                "origin_component": runtime_component_name,
                "origin_version": item.get("version"),
                "license_files": item.get("license_files", []),
                "audit_status": item.get("audit_status", "origin-and-license-document-linked"),
            }

    if _within(source, site_packages):
        return {
            "origin_type": "python-site-packages",
            "origin_component": None,
            "origin_version": None,
            "license_files": [],
            "audit_status": "package-owner-unresolved",
        }
    if _within(source, python_root):
        name = "Tcl/Tk" if source.name.casefold().startswith(("tcl", "tk")) else "Python"
        item = next((component for component in components if component["name"] == name), {})
        return {
            "origin_type": "python-runtime",
            "origin_component": name,
            "origin_version": item.get("version"),
            "license_files": item.get("license_files", []),
            "audit_status": "runtime-origin-found-license-scope-review-required",
        }
    if _within(source, system_root):
        return {
            "origin_type": "windows-system",
            "origin_component": "Windows system binary",
            "origin_version": None,
            "license_files": [],
            "audit_status": "windows-license-review-required",
        }
    return {
        "origin_type": "external-build-environment",
        "origin_component": None,
        "origin_version": None,
        "source_hint": _source_hint(source),
        "license_files": [],
        "audit_status": "external-origin-and-license-unresolved",
    }


def collect_native_artifact_inventory(
    distribution_dir: Path,
    toc_path: Path | None,
    components: list[dict],
    site_packages: Path,
    python_root: Path,
    system_root: Path | None,
) -> list[dict]:
    sources = _load_sources(toc_path)
    owners = _package_owners(site_packages)
    artifacts = []
    for path in sorted(distribution_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue
        relative = path.relative_to(distribution_dir).as_posix()
        source_entry = sources.get(relative.casefold())
        if source_entry is None:
            origin = {
                "origin_type": "unknown",
                "origin_component": None,
                "origin_version": None,
                "license_files": [],
                "audit_status": "build-source-unavailable",
            }
        else:
            origin = _attribute(
                source_entry[0], source_entry[1], owners, components,
                site_packages, python_root, system_root,
            )
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        artifacts.append({
            "path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            **origin,
        })
    return artifacts
