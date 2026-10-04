"""Render declared Python dependencies with their environment and purpose."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path


_REQUIREMENT = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<suffix>.*)$")


def normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirement_manifest(text: str, source: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        requirement = raw_line.split("#", 1)[0].strip()
        if not requirement:
            continue
        if requirement.startswith("-"):
            raise ValueError(f"{source}:{line_number}: pip options/includes are unsupported")
        match = _REQUIREMENT.fullmatch(requirement)
        if match is None:
            raise ValueError(f"{source}:{line_number}: unsupported requirement: {requirement}")
        entries.append((match.group("name"), requirement))
    return entries


def _manifest_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"dependency manifest path must stay in the repository: {value}")
    return root / relative


def _escaped_cell(value: str) -> str:
    return value.replace("|", r"\|")


def render_dependency_inventory(root: Path, manifests: list[Mapping[str, object]]) -> str:
    lines = [
        "# Python dependency inventory",
        "",
        "Generated from the dependency manifests configured in tools/docs/config.json.",
        "Repeated distributions are intentional when separate runtime environments need their own installation.",
        "",
    ]

    for manifest in manifests:
        source = str(manifest["path"])
        path = _manifest_path(root, source)
        entries = parse_requirement_manifest(path.read_text(encoding="utf-8"), source)
        rationales = manifest.get("packages")
        if not isinstance(rationales, Mapping):
            raise ValueError(f"{source}: packages rationale map is required")

        normalized_rationales = {
            normalize_distribution(str(name)): str(reason).strip()
            for name, reason in rationales.items()
        }
        normalized_entries = [normalize_distribution(name) for name, _ in entries]
        if len(set(normalized_entries)) != len(normalized_entries):
            raise ValueError(f"{source}: duplicate distributions are not allowed")

        declared = set(normalized_entries)
        described = set(normalized_rationales)
        missing = sorted(declared - described)
        obsolete = sorted(described - declared)
        if missing or obsolete:
            details = []
            if missing:
                details.append("missing rationales: " + ", ".join(missing))
            if obsolete:
                details.append("rationales without requirements: " + ", ".join(obsolete))
            raise ValueError(f"{source}: " + "; ".join(details))
        if any(not reason for reason in normalized_rationales.values()):
            raise ValueError(f"{source}: dependency rationale cannot be empty")

        environment = _escaped_cell(str(manifest["environment"]))
        purpose = str(manifest["purpose"]).strip()
        lines.extend(
            [
                f"## {source} — {environment}",
                "",
                purpose,
                "",
                "| Distribution | Requirement | Purpose |",
                "| --- | --- | --- |",
            ]
        )
        for name, requirement in entries:
            reason = normalized_rationales[normalize_distribution(name)]
            lines.append(
                f"| {_escaped_cell(name)} | {_escaped_cell(requirement)} | {_escaped_cell(reason)} |"
            )
        lines.append("")

    return "\n".join(lines)
