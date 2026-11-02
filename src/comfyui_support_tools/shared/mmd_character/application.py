"""Route, validate, locally repair, preview, and export MMD characters."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    CharacterCreationBackend,
    CharacterFinding,
    CharacterPreviewBackend,
    CharacterProvenance,
    CharacterRepairBackend,
    CharacterSpec,
    PmxCharacterDocument,
    PmxExportBackend,
)
from .validation import validate_character

CHARACTER_ROUTES = frozenset({"stable_humanoid", "free_3d"})
MAX_REPAIR_ROUNDS = 3


# {
# 責務: [CharacterRoute: route backend and feature capability declaration]
# フィールド: [route name, generation backend, capability tags]
# 処理: [route stable humanoid and free 3D generation to interchangeable adapters]
# }
@dataclass(frozen=True)
class CharacterRoute:
    name: str
    backend: CharacterCreationBackend
    capabilities: frozenset[str]


# {
# 責務: [CharacterCreationResult: chosen document and validation/export artifacts]
# フィールド: [document, provenance, findings, PMX, previews, report path]
# 処理: [provide an auditable candidate selection result]
# }
@dataclass(frozen=True)
class CharacterCreationResult:
    document: PmxCharacterDocument
    provenance: CharacterProvenance
    findings: tuple[CharacterFinding, ...]
    pmx_path: Path
    preview_paths: tuple[Path, ...]
    report_path: Path


# {
# 責務: [CharacterValidationError: expose rejected candidate diagnostics]
# フィールド: [findings: remaining error-level findings]
# 処理: [prevent invalid geometry/rig/morph/physics from reaching exporter]
# }
class CharacterValidationError(ValueError):
    # {
    # 責務: [__init__: create exception with structured diagnostics]
    # 処理: [retain findings for UI and logs]
    # 引数: [findings: unrepaired validation errors]
    # 戻り値: [None: initialized exception]
    # }
    def __init__(self, findings: tuple[CharacterFinding, ...]):
        self.findings = findings
        super().__init__("Character candidate did not pass required validation")


# {
# 責務: [CharacterRouteRegistry: manage stable/free geometry generation adapters]
# フィールド: [route descriptor map]
# 処理: [select appropriate route by explicit request or character type]
# }
class CharacterRouteRegistry:
    # {
    # 責務: [__init__: initialize empty route catalog]
    # 処理: [prepare stable humanoid and free-3D adapter registration]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized registry]
    # }
    def __init__(self):
        self._routes: dict[str, CharacterRoute] = {}

    # {
    # 責務: [register: register one unique known character generation route]
    # 処理: [reject duplicate route names and unsupported capabilities]
    # 引数: [name: stable_humanoid/free_3d, backend: creator, capabilities]
    # 戻り値: [None: route stored]
    # }
    def register(
        self, name: str, backend: CharacterCreationBackend, capabilities: frozenset[str]
    ) -> None:
        if name not in CHARACTER_ROUTES or name in self._routes:
            raise ValueError("route must be unique and one of stable_humanoid/free_3d")
        self._routes[name] = CharacterRoute(name, backend, capabilities)

    # {
    # 責務: [select: choose route based on explicit selection or humanoid compatibility]
    # 処理: [prefer stable route for anime humanoids and free geometry for other types]
    # 引数: [spec: character intent, route: optional explicit route]
    # 戻り値: [CharacterRoute: selected generation adapter]
    # }
    def select(self, spec: CharacterSpec, route: str | None = None) -> CharacterRoute:
        selected = route or spec.route
        if selected == "auto":
            selected = (
                "stable_humanoid"
                if spec.character_type in {"anime_humanoid", "humanoid", "vtuber"}
                else "free_3d"
            )
        if selected not in CHARACTER_ROUTES or selected not in self._routes:
            raise LookupError(f"no character generator is registered for route {selected!r}")
        return self._routes[selected]


# {
# 責務: [MmdCharacterCreator: orchestrate generated candidate quality and PMX delivery]
# フィールド: [route registry, repair adapter, preview adapter, PMX exporter]
# 処理: [select route, local repair, license check, preview, and no-overwrite export]
# }
class MmdCharacterCreator:
    # {
    # 責務: [__init__: configure optional creator pipeline adapters]
    # 処理: [keep model/repair/preview/export runtimes injected and independently replaceable]
    # 引数: [routes: route registry, repairer, previewer, exporter]
    # 戻り値: [None: initialized creator]
    # }
    def __init__(
        self,
        routes: CharacterRouteRegistry | None = None,
        repairer: CharacterRepairBackend | None = None,
        previewer: CharacterPreviewBackend | None = None,
        exporter: PmxExportBackend | None = None,
    ):
        self.routes = routes or CharacterRouteRegistry()
        self.repairer = repairer
        self.previewer = previewer
        self.exporter = exporter

    # {
    # 責務: [create: generate, rank, validate, locally repair, and optionally export character candidates]
    # 処理: [require clean provenance and block PMX export while error findings remain]
    # 引数: [spec: prompt/reference request, output_dir: optional destination, route: optional override]
    # 戻り値: [CharacterCreationResult: best valid character artifact and report]
    # }
    def create(
        self,
        spec: CharacterSpec,
        output_dir: Path,
        *,
        route: str | None = None,
    ) -> CharacterCreationResult:
        _validate_spec(spec)
        selected = self.routes.select(spec, route)
        provenance = selected.backend.provenance(spec)
        _validate_provenance(provenance, spec)
        candidates = selected.backend.generate_candidates(spec)
        if not candidates:
            raise ValueError("character backend returned no candidates")
        ranked = []
        for candidate in candidates[: spec.candidate_count]:
            repaired, findings = self._repair(candidate)
            errors = sum(item.severity == "error" for item in findings)
            warnings = sum(item.severity == "warning" for item in findings)
            ranked.append(((errors, warnings, -len(repaired.mesh.vertices)), repaired, findings))
        _score, document, findings = min(ranked, key=lambda item: item[0])
        if any(item.severity == "error" for item in findings):
            raise CharacterValidationError(findings)
        if self.exporter is None:
            raise RuntimeError("PMX export requires a configured PmxExportBackend")
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        if any(item.code == "model.name.unsafe" for item in findings):
            raise CharacterValidationError(findings)
        pmx_path = destination / f"{document.model_name}.pmx"
        report_path = destination / f"{document.model_name}.character.json"
        reserved = []
        temporaries = []
        previews = ()
        try:
            for path in (pmx_path, report_path):
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
                reserved.append(path)
            with tempfile.NamedTemporaryFile(
                dir=destination, prefix=f".{document.model_name}.", suffix=".pmx", delete=False
            ) as stream:
                pmx_temporary = Path(stream.name)
            pmx_temporary.unlink()
            temporaries.append(pmx_temporary)
            exported = self.exporter.export(document, pmx_temporary)
            if Path(exported) != pmx_temporary or not pmx_temporary.is_file():
                raise ValueError("PMX exporter must write the requested temporary path")
            os.replace(pmx_temporary, pmx_path)
            previews = self.previewer.preview(document, destination) if self.previewer else ()
            report = _build_report(spec, selected.name, provenance, findings, document, previews)
            payload = (
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            ).encode("utf-8")
            with tempfile.NamedTemporaryFile(
                dir=destination, prefix=f".{document.model_name}.", delete=False
            ) as stream:
                stream.write(payload)
                report_temporary = Path(stream.name)
            temporaries.append(report_temporary)
            os.replace(report_temporary, report_path)
            temporaries.clear()
        except BaseException:
            for path in reserved:
                path.unlink(missing_ok=True)
            raise
        finally:
            for path in temporaries:
                path.unlink(missing_ok=True)
        return CharacterCreationResult(
            document, provenance, findings, pmx_path, previews, report_path
        )

    # {
    # 責務: [_repair: run bounded local repair rounds for one candidate]
    # 処理: [revalidate after each repair and stop when valid or unrepairable]
    # 引数: [document: generation candidate]
    # 戻り値: [tuple[document, findings]: repaired candidate and latest validation]
    # }
    def _repair(self, document: PmxCharacterDocument):
        findings = validate_character(document)
        for _round in range(MAX_REPAIR_ROUNDS):
            errors = tuple(item for item in findings if item.severity == "error")
            if not errors or self.repairer is None or not any(item.repairable for item in errors):
                break
            document = self.repairer.repair(document, findings)
            next_findings = validate_character(document)
            if len(next_findings) >= len(findings) and next_findings == findings:
                break
            findings = next_findings
        return document, findings


# {
# 責務: [_validate_spec: validate prompt, references, route, and proportion limits]
# 処理: [reject missing input, unsafe dimensions, or invalid candidate counts]
# 引数: [spec: user character request]
# 戻り値: [None: valid spec or ValueError]
# }
def _validate_spec(spec: CharacterSpec) -> None:
    if not spec.prompt.strip() and not spec.references:
        raise ValueError("a prompt or at least one reference image is required")
    if spec.route not in {"auto", *CHARACTER_ROUTES}:
        raise ValueError("route must be auto, stable_humanoid, or free_3d")
    if not 0.8 <= spec.height <= 3.5 or not 4 <= spec.head_ratio <= 12:
        raise ValueError("character height/head ratio is outside supported proportions")
    if not 0.05 <= spec.shoulder_ratio <= 0.6 or not 0.05 <= spec.hip_ratio <= 0.6:
        raise ValueError("shoulder/hip proportions must be within 0.05..0.6")
    if not 1 <= spec.candidate_count <= 8:
        raise ValueError("candidate_count must be within 1..8")
    if any(not path.is_file() for path in spec.references):
        raise FileNotFoundError("one or more character references are missing")


# {
# 責務: [_validate_provenance: require explicit usable source model license data]
# 処理: [block absent/unknown license evidence before publishing generated bundles]
# 引数: [provenance: backend source/license statement, spec: reference sources]
# 戻り値: [None: allowed provenance or ValueError]
# }
def _validate_provenance(provenance: CharacterProvenance, spec: CharacterSpec) -> None:
    if not provenance.backend.strip() or not provenance.model_version.strip():
        raise ValueError("backend and model version provenance are required")
    if provenance.license_id.casefold() in {"", "unknown", "noassertion", "unverified"}:
        raise ValueError("model license must be explicit before creating export artifacts")
    if spec.references and not provenance.sources:
        raise ValueError("reference images must be included in provenance")


# {
# 責務: [_build_report: serialize character model provenance and validation outcome]
# 処理: [record route, prompt, reference paths, license, skeleton, morphs, physics, findings]
# 引数: [spec: request, route: chosen generation mode, provenance, findings, document, previews]
# 戻り値: [dict: portable JSON report]
# }
def _build_report(spec, route, provenance, findings, document, previews):
    return {
        "schema_version": 1,
        "model_name": document.model_name,
        "prompt": spec.prompt,
        "references": [str(path) for path in spec.references],
        "route": route,
        "seed": spec.seed,
        "provenance": {
            "backend": provenance.backend,
            "model_version": provenance.model_version,
            "license": provenance.license_id,
            "sources": provenance.sources,
        },
        "geometry": {
            "vertices": len(document.mesh.vertices),
            "triangles": len(document.mesh.triangles),
        },
        "bones": [bone.name for bone in document.bones],
        "morphs": [morph.name for morph in document.morphs],
        "physics": {"rigid_bodies": len(document.rigid_bodies), "joints": len(document.joints)},
        "previews": [str(path) for path in previews],
        "findings": [
            {
                "code": item.code,
                "severity": item.severity,
                "location": item.location,
                "message": item.message,
            }
            for item in findings
        ],
    }
